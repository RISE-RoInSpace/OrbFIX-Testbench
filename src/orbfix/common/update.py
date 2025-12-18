import os
import time
import zlib
import struct
import curses

from ..cmds.base import _encode_frame
from .RISECommand import RISECommand  # to parse returned frames
from ..transport.serial_rs422 import RiseParser, _fsm_decode_byte

FILE_TRANSFER_CMD = 0x0005  # 16-bit command id used for transfer

def send_orbfix_zip(
    ser,
    output_win,
    lock,
    log_file,
    zip_path: str | None = None,
    sys_id_val: int = 0,
    ack_timeout_s: float = 2.5,
    retry_once: bool = True,
):
    """
    Send a firmware blob via FILE_TRANSFER_CMD (0x0005) in framed packets.
    Payload per frame: [status:1][idx:u16][data...]
      - status=0 for metadata frame 
      - status=1 for data frames

    After each frame, wait for an ACK frame from the device and proceed only on OK.
    ACK format assumed: [status:u8][code:u16][msg:ascii...] where status==0 => OK.
    """

    # Resolve firmware path
    if zip_path is None:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base_dir = os.getcwd()
        zip_path = os.path.join(base_dir, "test_zip", "OrbFixApp.zip")
    else:
        if os.path.isdir(zip_path):
            zip_path = os.path.join(zip_path, "OrbFixApp.zip")
    zip_path = os.path.normpath(os.path.abspath(zip_path))

    # Logging helper
    def _log_line(s: str):
        with lock:
            try:
                output_win.addstr(s + "\n")
            except curses.error:
                output_win.scroll(1)
                output_win.addstr(s + "\n")
            output_win.refresh()
            log_file.write(f"{str(s)}\n")
            log_file.flush()

    # Parse ACK helper
    def _parse_ack_frame(frame_bytes: bytes):
        try:
            rc = RISECommand(frame_bytes)
            p = rc.payload or b""
            # Optional: enforce same command id if available on rc
            # if getattr(rc, "cmd_id", None) not in (None, FILE_TRANSFER_CMD):
            #     return (False, -4, f"unexpected cmd_id {rc.cmd_id}")
        except Exception as e:
            return (False, -3, f"ack decode error: {e}")

        # Empty payload = ACK
        if len(p) == 0:
            return (True, 0, "empty ACK")

        # Legacy/extended ACK: [status:u8][code:u16][msg...]
        if len(p) >= 3:
            status = p[0]
            code = int.from_bytes(p[1:3], "big")
            msg = p[3:].decode("ascii", errors="replace") if len(p) > 3 else ""
            ok = (status == 0)
            return (ok, code, msg)

        # Anything else is too short to parse
        return (False, -2, "ack too short")

    # Read frames until timeout and return first ACK verdict + stats
    def _wait_ack(timeout_s: float):
        parser = RiseParser()
        deadline = time.monotonic() + timeout_s
        bytes_seen = 0
        frames_seen = 0
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if not chunk:
                time.sleep(0.01)
                continue
            bytes_seen += len(chunk)
            for ch in chunk:
                flen = _fsm_decode_byte(parser, ch)
                if flen > 0:
                    frame = bytes(parser.buffer[:flen])
                    frames_seen += 1
                    ok, code, msg = _parse_ack_frame(frame)
                    if ok or code in (-2, -3):  # valid or decodable result; return verdict
                        return (ok, code, msg, frame, {"bytes_seen": bytes_seen, "frames_seen": frames_seen})
                    # If not an ACK format, keep waiting
        return (False, -1, "ack timeout", b"", {"bytes_seen": bytes_seen, "frames_seen": frames_seen})

    # Validate file
    if not os.path.isfile(zip_path):
        _log_line(f"[0x0005] ERROR: zip file not found at {zip_path}")
        return

    try:
        with open(zip_path, "rb") as f:
            data = f.read()
    except OSError as e:
        _log_line(f"[0x0005] ERROR: could not read zip: {e}")
        return

    total_size = len(data)
    if total_size == 0:
        _log_line(f"[0x0005] ERROR: zip file is empty ({zip_path})")
        return

    # Compute CRC32
    crc32_val = zlib.crc32(data) & 0xFFFFFFFF
    checksum64 = crc32_val

    # Max encoded ~1024
    MAX_FRAME = 1024
    HEADER_AND_TAIL = 9 + 1   # encoder overhead assumption
    PER_PACKET_META = 1 + 2   # status + idx in payload
    max_chunk = MAX_FRAME - HEADER_AND_TAIL - PER_PACKET_META
    if max_chunk <= 0:
        max_chunk = 512

    total_packets = (total_size + max_chunk - 1) // max_chunk
    if total_packets > 0xFFFF:
        _log_line(f"[0x0005] ERROR: too many packets ({total_packets}) for uint16 idx")
        return

    # Send + ACK helper (drains stale input, sends, then waits for ACK with stats)
    def _send_wait_ack(info: str, payload: bytes) -> bool:
        try:
            frame = _encode_frame(FILE_TRANSFER_CMD, sys_id_val, payload)
        except Exception as e:
            _log_line(f"[0x0005] ERROR: _encode_frame failed during {info}: {e}")
            return False

        # Drain stale input before sending
        try:
            ser.reset_input_buffer()
            _ = ser.read(ser.in_waiting or 0)
        except Exception:
            pass

        try:
            ser.write(frame)
        except Exception as e:
            _log_line(f"[0x0005] Write error during {info}: {e}")
            return False

        hexstr = " ".join(f"{b:02X}" for b in frame)
        _log_line(f"→ Sent 0x0005 {info}: {hexstr!r}")

        ok, code, msg, _f, stats = _wait_ack(ack_timeout_s)
        if ok:
            if msg:
                _log_line(f"← ACK {info}: code={code} msg='{msg}' bytes_seen={stats['bytes_seen']} frames_seen={stats['frames_seen']}")
            else:
                _log_line(f"← ACK {info}: code={code} bytes_seen={stats['bytes_seen']} frames_seen={stats['frames_seen']}")
            return True

        # Distinguish silence vs. non-ACK traffic
        if code == -1 and stats["bytes_seen"] == 0:
            _log_line(f"← TIMEOUT {info}: no bytes received in {ack_timeout_s:.2f}s")
        elif code == -1 and stats["bytes_seen"] > 0:
            _log_line(f"← TIMEOUT {info}: bytes_seen={stats['bytes_seen']} frames_seen={stats['frames_seen']} (no valid ACK)")
        else:
            _log_line(f"← NAK {info}: code={code} msg='{msg}' bytes_seen={stats['bytes_seen']} frames_seen={stats['frames_seen']}")
        return False

    # 1) Metadata frame: >BHQQ (status=0, total_packets:u16, checksum64:u64, total_size:u64)
    meta_payload = struct.pack(">BHQQ", 0, total_packets, checksum64, total_size)
    if not _send_wait_ack(f"meta packets={total_packets} size={total_size}", meta_payload):
        return  # fail meta without retry by default

    # 2) Data frames: [status=1][idx:u16][chunk...], ACK per packet
    sent = 0
    for idx in range(total_packets):
        start = idx * max_chunk
        end = min(start + max_chunk, total_size)
        chunk = data[start:end]
        data_payload = struct.pack(">BH", 1, idx) + chunk

        if _send_wait_ack(f"chunk {idx + 1}/{total_packets} sz={len(chunk)}", data_payload):
            pass
        else:
            if retry_once:
                _log_line(f"[0x0005] retrying packet idx={idx}")
                if not _send_wait_ack(f"chunk {idx + 1}/{total_packets} RETRY sz={len(chunk)}", data_payload):
                    _log_line(f"[0x0005] ERROR: packet idx={idx} failed after retry; aborting")
                    return
            else:
                _log_line(f"[0x0005] ERROR: packet idx={idx} failed; aborting")
                return

        sent += len(chunk)
        if (idx & 0x1F) == 0 or sent == total_size:
            pct = 100.0 * sent / total_size if total_size else 100.0
            _log_line(f"[0x0005] progress {sent}/{total_size} bytes ({pct:.1f}%)")

    _log_line(f"[0x0005] Transfer of {zip_path} complete: {total_packets} packets, {total_size} bytes")
