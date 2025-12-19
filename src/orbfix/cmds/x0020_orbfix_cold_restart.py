from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..common.config import get_default_port
from pathlib import Path
from serial import SerialException

app = typer.Typer(help="Performs a cold restart of OrbFIX-NXP")

CMD_ID = 0x0020
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_orbfix_cold_restart(decoded):
    """
    Command 0x0020: OrbFix NXP Cold restart (Set)
    Payload: Empty
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""
    return (f"Incoming (hex): {pl.hex()}", {"payload_hex": pl.hex()})

@app.command("set")
def orbfix_cold_restart(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # payload: str | None = typer.Option(None, "--payload", help="Command/payload (string)"),
):
    """
    OrbFix NXP Cold restart

    Examples:
        orbfix cmd orbfix-cold-restart set
    """
    
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
    from pathlib import Path

    saved = get_default_port()
    resolved_port = port or (saved if saved and Path(saved).exists() else None)
    if not resolved_port:
        import typer as _t

        _t.secho("No valid port. Use --port, --auto, or set a saved port.", fg="red")
        raise _t.Exit(code=2)

    payload_bytes = parse_payload_spec("")

    typer.secho("Sending OrbFix NXP Cold restart:", fg="cyan", bold=True)
    typer.echo()

    from serial import SerialException

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
