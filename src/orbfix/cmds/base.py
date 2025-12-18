from __future__ import annotations

import time
from typing import List, Optional, Tuple

import serial

from ..common.io_utils import hexdump
from ..transport.serial_rs422 import open_serial, read_frames
from ..common import RISECommand as RS
from .parsers import parse_decoded

try:
    from ..transport.serial_rs422 import open_serial_by_vidpid  # type: ignore
except Exception:  # pragma: no cover
    open_serial_by_vidpid = None  # type: ignore

DEFAULT_OVERALL_WAIT_S = 2.0

__all__ = ["send_and_receive", "DEFAULT_OVERALL_WAIT_S"]


def _encode_frame(cmd_id: int, sysid: int, payload: bytes) -> bytes:
    """
    Be tolerant to either of these userland RS helpers:
      - RS.riseprotocol_encode(cmd_id, sysid, payload)
      - RS.riseprotocol_encode(cmd_id, payload)
    """
    try:
        return RS.riseprotocol_encode(cmd_id, sysid, payload)
    except TypeError:
        # Fallback: without sysid
        return RS.riseprotocol_encode(cmd_id, payload) 


def send_and_receive(
    port: str,
    baudrate: int,
    read_timeout_s: float,
    overall_wait_s: float,
    cmd_id: int,
    sysid: int,
    payload: bytes,
    decode: bool = True,
    encode: bool = True,
    *,
    require_eol: bool = True,
    retries: int = 1,
    reopen_vid_pid: Optional[Tuple[str, str]] = None,
    reopen_wait_s: float = 30.0,
    debug_hex: bool = True,
    pre_flush: bool = True,
) -> List[bytes]:
    attempt = 0
    frames: List[bytes] = []

    def _open() -> serial.Serial:
        if attempt > 0 and reopen_vid_pid and open_serial_by_vidpid:
            vid, pid = reopen_vid_pid
            print(f"[i] Reopening by VID:PID {vid}:{pid} (attempt {attempt}/{retries})...")
            return open_serial_by_vidpid(vid, pid, baudrate=baudrate, timeout_s=read_timeout_s, wait_s=reopen_wait_s)
        return open_serial(port, baudrate=baudrate, timeout_s=read_timeout_s)

    while True:
        attempt += 1
        try:
            with _open() as ser:
                print(f"Connected to {ser.port} @ {baudrate}")

                # === FLUSH AND DRAIN BEFORE COMMAND ===
                if pre_flush:
                    ser.reset_input_buffer()   # Clear OS RX buffer
                    ser.reset_output_buffer()  # Clear OS TX buffer

                    # Drain any residual data from device
                    drain_deadline = time.monotonic() + 0.05
                    drained = bytearray()
                    while time.monotonic() < drain_deadline:
                        chunk = ser.read(ser.in_waiting or 1)
                        if not chunk:
                            break
                        drained.extend(chunk)

                    if drained and debug_hex:
                        print(f"[DRAINED] {len(drained)} bytes: {drained.hex(' ')}")

                # Build TX buffer
                if encode:
                    encoded = _encode_frame(cmd_id, sysid, payload)
                    print(f"Sent (encoded): {hexdump(encoded)} ({len(encoded)} bytes)")
                else:
                    encoded = payload
                    print(f"Sent (raw/no-encode): {hexdump(encoded)} ({len(encoded)} bytes)")

                ser.write(encoded)
                ser.flush()  # Ensure data is transmitted to device

                deadline = time.monotonic() + overall_wait_s
                frames = read_frames(
                    ser,
                    deadline,
                    require_eol=require_eol,
                    debug_hex=debug_hex,
                )
        except (serial.SerialException, OSError, ValueError) as e:
            print(f"[warn] Serial error: {e}")

        if frames:
            break

        if attempt > retries:
            print("Warning: No response received before timeout.")
            return []

        time.sleep(0.1)

    # Pretty-print and decode frames
    for idx, frame in enumerate(frames, 1):
        print(f"\nFrame {idx} [{len(frame)} bytes]: {hexdump(frame)}")
        if not decode:
            continue

        decoded, err = RS.riseprotocol_decode(frame)
        if err != 0:
            print(f"  Decode error: {err}")
            continue

        print("  Decoded:")
        print("     Start: RS")
        if hasattr(decoded, "crc"):
            print(f"     CRC: 0x{decoded.crc:04X}")

        sys_field = next((f for f in ("orbfix_id", "system", "system_id") if hasattr(decoded, f)), None)
        if sys_field:
            print(f"     System ID: 0x{getattr(decoded, sys_field):02X}")
        if hasattr(decoded, "cmd_id"):
            print(f"     Command ID: 0x{decoded.cmd_id:04X}")
        if hasattr(decoded, "payload_length"):
            print(f"     Payload length: {decoded.payload_length}")

        human, _meta = parse_decoded(decoded)
        print("  Parsed:")
        for line in human.splitlines():
            print(f"     {line}")

    return frames

