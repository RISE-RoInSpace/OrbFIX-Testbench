from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the clock sync threshold.")

CMD_ID = 0x0016
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_troposphere_model(decoded):
    """
    Command 0x000E: Troposphere Model (Get/Set)
    Payload: 2 bytes
      - Byte 0 (U1): Zenith Model
      - Byte 1 (U1): Mapping Model
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 1:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    zenith = pl[0]
    mapping = pl[1]

    # Zenith Model mapping
    zenith_map = {
        0x00: "Off",
        0x01: "Saastamoinen",
        0x02: "MOPS",
    }

    # Mapping Model mapping
    mapping_map = {
        0x00: "Niell",
        0x01: "MOPS",
    }

    zenith_str = zenith_map.get(zenith, f"Unknown(0x{zenith:02X})")
    mapping_str = mapping_map.get(mapping, f"Unknown(0x{mapping:02X})")

    result = "Troposphere Model:\n"
    result += f"  Zenith Model: {zenith_str}\n"
    result += f"  Mapping Model: {mapping_str}\n"

    return (
        result,
        {
            "zenith": zenith_str,
            "zenith_value": zenith,
            "mapping": mapping_str,
            "mapping_value": mapping,
        }
    )

@app.command("set")
def set_troposphere_model(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    zenith: str = typer.Option(None, "--zenith-model", "-z", help="Zenith Model: off, saastamoinen, mops"),
    mapping: str = typer.Option(None, "--mapping-model", "-m", help="Mapping Model: niell, mops"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Troposphere Model configuration.

    Examples:
      # Set all parameters
      orbfix cmd troposphere-model set --zenith-model mops --mapping-model niell

    # Raw payload
      orbfix cmd troposphere-model set --payload 0101
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
        if len(payload_bytes) != 2:
            typer.secho(f"Warning: Payload is {len(payload_bytes)} bytes (expected 2)", fg="yellow")
    else:
        # All parameters required for SET
        if not all([zenith, mapping]):
            typer.secho("Error: All parameters required: --zenith-model --mapping-model", fg="red")
            raise typer.Exit(code=1)

        # Zenith Model mapping
        zenith_map = {
            "off": 0x00,
            "saastamoinen": 0x01,
            "mops": 0x02,
        }

        # Mapping
        mapping_map = {
            "niell": 0x00,
            "mops": 0x01,
        }

        # Parse and validate
        zenith_lower = zenith.lower()
        if zenith_lower not in zenith_map:
            typer.secho(f"Error: Unknown satellite '{zenith}'", fg="red")
            typer.secho(f"Valid values: {', '.join(zenith_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        zenith_byte = zenith_map[zenith_lower]

        mapping_lower = mapping.lower()
        if mapping_lower not in mapping_map:
            typer.secho(f"Error: Unknown satellite '{mapping}'", fg="red")
            typer.secho(f"Valid values: {', '.join(mapping_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        mapping_byte = mapping_map[mapping_lower]

        payload_bytes = bytes([zenith_byte, mapping_byte])

        # Show configuration
        typer.secho("\nTroposphere Model Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Zenith Model: {zenith}", fg="green")
        typer.secho(f"  Mapping: {mapping}", fg="green")
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
def get_troposphere_model(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current Troposphere Model configuration."""
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
