from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..common.config import get_default_port
from pathlib import Path
from serial import SerialException

app = typer.Typer(help="Reset OrbFIX-GNSSs")

CMD_ID = 0x0003
DEFAULT_SYSID = "0x7A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_command(decoded):
    pl: bytes = getattr(decoded, "payload", b"") or b""
    
    return (f"Incoming (hex): {pl.hex()}", {"payload_hex": pl.hex()})

@app.command("set")
def reset_orbfix_gnss(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    auto: bool = typer.Option(False, help="Auto-detect USB device by VID/PID"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    payload: str | None = typer.Option(None, "--payload", help="Command/payload (string)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    # parse sysid -> int
    sys_id_val = parse_one_byte_spec(sysid, what="system id")
    if sys_id_val is None:
        typer.secho(f"Invalid system id spec: {sysid!r}", fg="red")
        raise typer.Exit(code=2)
    
    # resolve serial port
    saved = get_default_port()
    resolved_port = None

    # if --auto requested, try to detect device
    if auto:
        detected = find_usb_device()
        if detected:
            resolved_port = detected
        else:
            typer.secho("Auto-detect failed to find a USB device.", fg="yellow")

    # explicit port / saved port fallback
    if not resolved_port:
        resolved_port = port or (saved if saved and Path(saved).exists() else None)

    if not resolved_port:
        typer.secho("No valid port. Use --port, --auto, or set a saved port.", fg="red")
        raise typer.Exit(code=2)

    payload_bytes = parse_payload_spec(payload or "")

    try:
        send_and_receive(
            port=resolved_port,
            baudrate=baud,
            read_timeout_s=timeout,
            overall_wait_s=wait,
            cmd_id=CMD_ID,
            sysid=sys_id_val,
            payload=payload_bytes,
            decode=(not no_decode),
        )
    except SerialException as e:
        typer.secho(f"Serial error: {e}", fg="red")
        raise typer.Exit(code=1)
