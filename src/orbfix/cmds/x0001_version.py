from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..common.monitor_proxy import try_monitor_proxy
from ..common import RISECommand as RS
from .parsers import parse_decoded

app = typer.Typer(help="Request OrbFIX firmware/version info.")

CMD_ID = 0x0001
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_version(decoded):
    pl: bytes = getattr(decoded, "payload", b"") or b""
    # Try ASCII/UTF-8 string first
    try:
        s = pl.rstrip(b"\x00").decode("utf-8")
        if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
            return (f"Version: {s}", {"version": s})
    except Exception:
        pass
    # 3-byte semantic version fallback
    if len(pl) == 3:
        major, minor, patch = pl
        return (f"Version: {major}.{minor}.{patch}",
                {"major": major, "minor": minor, "patch": patch})
    return (f"Version payload (hex): {pl.hex()}", {"payload_hex": pl.hex()})

@app.command("get")
def get_version(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
    from ..transport.serial_rs422 import find_usb_device
    from pathlib import Path
    saved = get_default_port()
    resolved_port = (
        port
        or (saved if saved and Path(saved).exists() else None)
    )
    if not resolved_port:
        import typer as _t
        _t.secho("No valid port. Use --port, --auto, or set a saved port.", fg="red")
        raise _t.Exit(code=2)

    payload = b""

    resp = try_monitor_proxy(CMD_ID, sys_id_val, payload, wait, decode=(not no_decode))
    if resp is not None:
        if resp.get("ok"):
            # Prefer local decoding: reconstruct frames from hex
            frames_hex = resp.get("frames_hex", [])
            if frames_hex and no_decode:
                # Raw frames
                for hx in frames_hex:
                    print(hx)
            elif frames_hex:
                for hx in frames_hex:
                    fr = bytes.fromhex(hx)
                    decoded, err = RS.riseprotocol_decode(fr)
                    if err == 0:
                        human, _m = parse_decoded(decoded)
                        print(human)
                    else:
                        print(f"[decode error] {err}")
            else:
                # Fallback to server human if no frames returned
                human = resp.get("human", "")
                if human:
                    print(human)
        else:
            print(resp.get("error", "monitor error"))
        return

    from serial import SerialException
    try:
        send_and_receive(
            port=resolved_port,
            baudrate=baud,
            read_timeout_s=timeout,
            overall_wait_s=wait,
            cmd_id=CMD_ID,
            sysid=sys_id_val,
            payload=payload,
            decode=(not no_decode),
        )
    except SerialException as e:
        typer.secho(f"Serial error: {e}", fg="red")
        raise typer.Exit(code=1)
