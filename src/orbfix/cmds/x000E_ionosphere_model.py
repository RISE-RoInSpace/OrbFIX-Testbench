from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the type of model used to correct ionospheric errors.")

CMD_ID = 0x000E
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_ionosphere_model(decoded):
    """
    Command 0x000E: Ionosphere Model (Get/Set)
    Payload: 4 bytes
      - Byte 0 (U1): Model
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 1:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    model = pl[0]

    # Model mapping
    model_map = {
        0x00: "Auto",
        0x01: "Off",
        0x02: "KlobucharGPS",
        0x03: "SBAS",
        0x04: "MultiFreq",
        0x05: "KlobucharBDS",
    }

    model_str = model_map.get(model, f"Unknown(0x{model:02X})")

    result = "Ionosphere Model:\n"
    result += f"  Model: {model_str}\n"

    return (
        result,
        {
            "model": model_str,
            "model_value": model,
        }
    )

@app.command("set")
def set_ionosphere_model(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    model: str = typer.Option(None, "--model", "-m", help="Model: auto, off, KlobucharGPS, sbas, multifreq, KlobucharBDS"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Ionosphere Model configuration.

    Examples:
      # Set all parameters
      orbfix cmd ionosphere-model set --model auto

    # Raw payload
      orbfix cmd ionosphere-model set --payload 03
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
        if not all([model]):
            typer.secho("Error: All parameters required: --model", fg="red")
            raise typer.Exit(code=1)

        # Model mapping
        model_map = {
            "auto": 0x00,
            "off": 0x01,
            "klobuchargps": 0x02,
            "sbas": 0x03,
            "multifreq": 0x04,
            "klobucharbds": 0x05,
        }

        # Parse and validate
        model_lower = model.lower()
        if model_lower not in model_map:
            typer.secho(f"Error: Unknown satellite '{model}'", fg="red")
            typer.secho(f"Valid values: {', '.join(model_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        model_byte = model_map[model_lower]

        payload_bytes = bytes([model_byte])

        # Show configuration
        typer.secho("\nIonosphere Model Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Model: {model}", fg="green")
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
def get_ionosphere_model(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current Ionosphere Model configuration."""
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
