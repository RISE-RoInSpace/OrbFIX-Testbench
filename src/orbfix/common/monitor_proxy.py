from __future__ import annotations
import os
import socket
import json

DEFAULT_SOCK = os.path.expanduser("~/.orbfix/monitor.sock")

def try_monitor_proxy(
    cmd_id: int,
    sysid: int,
    payload: bytes,
    wait: float,
    decode: bool = True,
    sock_path: str = DEFAULT_SOCK,
):
    """
    Send a command request to the running monitor via Unix socket and return the JSON reply dict.
    Returns None if the monitor isn't running or on connection error.
    """
    if not os.path.exists(sock_path):
        return None

    req = {
        "cmd_id": cmd_id,
        "sysid": sysid,
        "payload_hex": payload.hex(),
        "wait": wait,
        "decode": decode,
    }

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(sock_path)
            s.sendall(json.dumps(req).encode("utf-8") + b"\n")
            s.settimeout(wait + 1.5)
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None
