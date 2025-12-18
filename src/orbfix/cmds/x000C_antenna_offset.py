from __future__ import annotations
import struct
import typer
from ..common.io_utils import parse_one_byte_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..common.config import get_default_port
from pathlib import Path
from serial import SerialException

app = typer.Typer(help="Set antenna offset for OrbFIX")

CMD_ID = 0x000C
DEFAULT_SYSID = "0x6A"

@register(CMD_ID)
def _parse_antenna_offset_response(decoded):
    pl: bytes = getattr(decoded, "payload", b"") or b""
    return (f"Incoming (hex): {pl.hex()}", {"payload_hex": pl.hex()})

@app.command("set")
def set_antenna_offset(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    auto: bool = typer.Option(False, help="Auto-detect USB device by VID/PID"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    delta_e: float = typer.Option(..., help="Antenna offset East (m)"),
    delta_n: float = typer.Option(..., help="Antenna offset North (m)"),
    delta_u: float = typer.Option(..., help="Antenna offset Up (m)"),
):
    """Set the antenna reference point offsets (ENU) for the GNSS system."""
    
    # parse sysid -> int
    sys_id_val = parse_one_byte_spec(sysid, what="system id")
    if sys_id_val is None:
        typer.secho(f"Invalid system id spec: {sysid!r}", fg="red")
        raise typer.Exit(code=2)
    
    # resolve serial port
    saved = get_default_port()
    resolved_port = None

    if auto:
        detected = find_usb_device()
        if detected:
            resolved_port = detected
        else:
            typer.secho("Auto-detect failed to find a USB device.", fg="yellow")

    resolved_port = resolved_port or port or (saved if saved and Path(saved).exists() else None)

    if not resolved_port:
        typer.secho("No valid port. Use --port, --auto, or set a saved port.", fg="red")
        raise typer.Exit(code=2)
    
    try:
        send_and_receive(
            port=resolved_port,
            baudrate=baud,
            read_timeout_s=timeout,
            overall_wait_s=wait,
            cmd_id=CMD_ID,
            sysid=sys_id_val,
            payload=payload_bytes,
            decode=True,
        )
    except SerialException as e:
        typer.secho(f"Serial error: {e}", fg="red")
        raise typer.Exit(code=1)

@app.command("get")
def get_antenna_offset(
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