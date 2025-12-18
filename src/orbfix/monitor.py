from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import typer

from .transport.serial_rs422 import open_serial, RiseParser, _fsm_decode_byte, RiseState
from .cmds.base import _encode_frame
from .common.RISECommand import RISECommand
from .cmds.parsers import parse_decoded

app = typer.Typer(help="OrbFIX monitor: keep serial open, stream NMEA, proxy commands.")

DEFAULT_SOCK = os.path.expanduser("~/.orbfix/monitor.sock")

'''
How to use
orbfix monitor start --port <port> --baud 115200 --udp-host 127.0.0.1 --udp-port 10110
'''
def _ensure_sock_dir(sock_path: str):
    p = Path(sock_path).parent
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass


def _drain(ser, ms: int = 50):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        _ = ser.read(ser.in_waiting or 1)


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass

    def flush(self):
        for stream in self.streams:
            stream.flush()


@app.command("start")
def start(
    port: str = typer.Option(..., "--port", help="Serial port"),
    baud: int = typer.Option(115200, "--baud", help="Baud rate"),
    sock: str = typer.Option(DEFAULT_SOCK, "--sock", help="Unix socket path"),
    udp_host: str = typer.Option("", "--udp-host", help="Optional UDP host for NMEA"),
    udp_port: int = typer.Option(10110, "--udp-port", help="Optional UDP port for NMEA"),
    log_file: str = typer.Option("", "--log-file", help="Path to append monitor output/NMEA"),
):
    import socket as pysock

    log_fp = None
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("a", encoding="utf-8")
        sys.stdout = _Tee(sys.stdout, log_fp)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, log_fp)  # type: ignore[assignment]

    _ensure_sock_dir(sock)
    stop_evt = threading.Event()
    ser_lock = threading.Lock()
    resp_evt = threading.Event()
    resp_frames: list[bytes] = []
    resp_text_lines: list[str] = []
    expected_cmd_id_box = {"val": None}

    udp_sock = None
    if udp_host:
        udp_sock = pysock.socket(pysock.AF_INET, pysock.SOCK_DGRAM)

    ser = open_serial(port, baudrate=baud, timeout_s=0.05)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    def reader():
        parser = RiseParser()
        buf = bytearray()
        ascii_mode = False  # NEW

        while not stop_evt.is_set():
            try:
                chunk = ser.read(512)
                if not chunk:
                    time.sleep(0.01)
                    continue

                for b in chunk:
                    # if we are inside a NMEA line, don't let the RISE FSM touch it
                    if ascii_mode:
                        buf.append(b)
                        if b == 0x0A:  # '\n'
                            ascii_mode = False
                        continue

                    # start ASCII mode on NMEA '$'
                    if b == 0x24:  # '$'
                        ascii_mode = True
                        buf.append(b)
                        continue

                    # Existing FSM path for non-NMEA bytes
                    state_before = parser.state
                    flen = _fsm_decode_byte(parser, b)
                    state_after = parser.state

                    if flen > 0:
                        frame = bytes(parser.buffer[:flen])

                        if resp_evt.is_set():
                            try:
                                dec = RISECommand(frame)
                                if expected_cmd_id_box["val"] is None or dec.cmd_id == expected_cmd_id_box["val"]:
                                    resp_frames.append(frame)
                            except Exception:
                                resp_frames.append(frame)

                    else:
                        if state_after == RiseState.ST_WAIT_SYNC1:
                            if state_before == RiseState.ST_WAIT_SYNC1 and b != 0x52:  # 'R'
                                buf.append(b)
                            elif state_before == RiseState.ST_WAIT_SYNC2:
                                buf.append(0x52)
                                buf.append(b)

                # Process complete ASCII lines (unchanged)
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        break
                    line = bytes(buf[:nl+1])
                    del buf[:nl+1]
                    try:
                        txt = line.decode("ascii", errors="replace").rstrip("\r\n")
                    except Exception:
                        txt = ""
                    if not txt:
                        continue

                    if txt.startswith("$"):
                        print(txt)
                        if udp_sock:
                            try:
                                udp_sock.sendto((txt + "\r\n").encode("ascii", errors="replace"), (udp_host, udp_port))
                            except Exception:
                                pass
                    elif resp_evt.is_set():
                        resp_text_lines.append(txt)
                    else:
                        print(txt)
                        if udp_sock:
                            try:
                                udp_sock.sendto((txt + "\r\n").encode("ascii", errors="replace"), (udp_host, udp_port))
                            except Exception:
                                pass

            except Exception as e:
                print(f"[reader] {e}", file=sys.stderr)
                time.sleep(0.05)


    def server():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(sock)
            srv.listen(8)
            while not stop_evt.is_set():
                try:
                    srv.settimeout(0.1)
                    try:
                        conn, _ = srv.accept()
                    except socket.timeout:
                        continue
                    with conn:
                        data = b""
                        conn.settimeout(1.0)
                        while True:
                            chunk = conn.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                            if data.endswith(b"\n"):
                                break

                        try:
                            req = json.loads(data.decode("utf-8"))
                        except Exception as e:
                            resp = {"ok": False, "error": f"bad json: {e}"}
                            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                            continue

                        try:
                            cmd_id = int(req.get("cmd_id"))
                            sysid = int(req.get("sysid"))
                            payload_hex = req.get("payload_hex", "")
                            payload = bytes.fromhex(payload_hex)
                            wait = float(req.get("wait", 2.0))
                            decode = bool(req.get("decode", True))
                        except Exception as e:
                            resp = {"ok": False, "error": f"bad fields: {e}"}
                            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                            continue

                        try:
                            with ser_lock:
                                # Clean buffers, then open capture window BEFORE writing
                                ser.reset_input_buffer()
                                ser.reset_output_buffer()
                                _drain(ser, 30)

                                resp_frames.clear()
                                resp_text_lines.clear()
                                expected_cmd_id_box["val"] = cmd_id
                                resp_evt.set()

                                enc = _encode_frame(cmd_id, sysid, payload)
                                ser.write(enc)
                                ser.flush()

                                # Wait for response
                                deadline = time.monotonic() + wait
                                while time.monotonic() < deadline and not stop_evt.is_set():
                                    time.sleep(0.02)

                                resp_evt.clear()
                                expected_cmd_id_box["val"] = None
                        except Exception as e:
                            resp = {"ok": False, "error": f"serial error: {e}"}
                            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                            continue

                        frames_hex = [f.hex() for f in resp_frames]
                        human_lines = []
                        if decode:
                            for fr in resp_frames:
                                try:
                                    decoded = RISECommand(fr)
                                    human, _meta = parse_decoded(decoded)
                                    human_lines += human.splitlines()
                                except Exception as e:
                                    human_lines.append(f"[decode error] {e}")

                        resp = {
                            "ok": True,
                            "frames_hex": frames_hex,
                            "text_lines": resp_text_lines,
                            "human": "\n".join(human_lines),
                        }
                        conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")

                except Exception as e:
                    print(f"[server-loop] {e}", file=sys.stderr)
        except Exception as e:
            print(f"[server] {e}", file=sys.stderr)
        finally:
            try:
                srv.close()
            except Exception:
                pass

    t_r = threading.Thread(target=reader, name="orbfix-mon-reader", daemon=True)
    t_s = threading.Thread(target=server, name="orbfix-mon-server", daemon=True)
    t_r.start()
    t_s.start()

    print(f"[monitor] started on {port}@{baud}, socket={sock}")
    if udp_sock:
        print(f"[monitor] UDP forwarding to {udp_host}:{udp_port}")

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        t_r.join(timeout=1.0)
        t_s.join(timeout=1.0)
        try:
            ser.close()
        except Exception:
            pass
        try:
            os.unlink(sock)
        except Exception:
            pass
        print("[monitor] stopped")
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass
