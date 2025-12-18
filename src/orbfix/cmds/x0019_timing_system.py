from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the reference time system for the computation of the receiver clock bias.")

CMD_ID = 0x0019
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_timing_system(decoded):
    """
    Command 0x0014: Timing System (Get/Set)
    Payload: 4 bytes
      - Byte 0 (U1): System
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 1:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    system = pl[0]

    # System mapping
    system_map = {
        0x00: "Galileo",
        0x01: "GPS",
        0x02: "BeiDou",
        0x03: "auto",
    }

    system_str = system_map.get(system, f"Unknown(0x{system:02X})")

    result = "Timing System:\n"
    result += f"  System: {system_str}\n"

    return (
        result,
        {
            "system": system_str,
            "system_value": system,
        }
    )

@app.command("set")
def set_timing_system(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    system: str = typer.Option(None, "--system", "-s", help="System: Galileo, GPS, BeiDou, auto"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Timing System configuration.

    Examples:
      # Set all parameters
      orbfix cmd timing-system set --system GPS

    # Raw payload
      orbfix cmd timing-system set --payload 01
    """
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
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

    # Build payload
    if payload:
        payload_bytes = parse_payload_spec(payload)
        if len(payload_bytes) != 1:
            typer.secho(f"Warning: Payload is {len(payload_bytes)} bytes (expected 1)", fg="yellow")
    else:
        # All parameters required for SET
        if not all([system]):
            typer.secho("Error: All parameters required: --system", fg="red")
            raise typer.Exit(code=1)

        # System mapping
        system_map = {
            "galileo": 0x00,
            "gps": 0x01,
            "beidou": 0x02,
            "auto": 0x03,
        }

        # Parse and validate
        system_lower = system.lower()
        if system_lower not in system_map:
            typer.secho(f"Error: Unknown system '{system}'", fg="red")
            typer.secho(f"Valid values: {', '.join(system_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        system_byte = system_map[system_lower]

        payload_bytes = bytes([system_byte])

        # Show configuration
        typer.secho("\nTiming System Configuration:", fg="cyan", bold=True)
        typer.secho(f"  System: {system}", fg="green")
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


@app.command("get")
def get_timing_system(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current Timing System configuration."""
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
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

    # Empty payload for GET
    payload_bytes = b""

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
