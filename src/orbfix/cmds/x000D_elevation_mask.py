from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Request OrbFIX firmware/version info.")

CMD_ID = 0x000d
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_elevation_mask(decoded):
    """
    Command 0x0014: Elevation Mask (Get/Set)
    Payload: 2 bytes
      - Byte 0 (X1): Engine
      - Byte 1 (I1): Mask
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 4:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    # Parse the 2 bytes
    bitfield_map = {
        0x00: "Tracking",
        0x01: "PVT",
        0x02: "all",
    }

    engine_str = []
    mask_values = []

    for i in range(0, len(pl), 2):     # 0, 2
        engine = pl[i]          # pl[0], pl[2]
        mask = int.from_bytes(pl[i+1:i+2], "big", signed=True)  # pl[1], pl[3]

        # Convert engine to text
        engine_str.append(bitfield_map.get(engine, f"Unknown({engine})"))
        mask_values.append(mask)
        if pl[2] == 0:
            break

    result = "Elevation Mask Level:\n"
    result += f"  Engine: {engine_str}\n"
    result += f"  Mask: {mask_values}\n"

    return (
        result,
        {
            "engine": engine_str,
            "mask": str(mask),
        }
    )

@app.command("set")
def set_elevation_mask(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    engine: str = typer.Option(None, "--engine", "-e", help="Engine : Tracking, PVT"),
    mask: str = typer.Option(None, "--mask", "-m", help="Mask: -90 ... 90"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Elevation Mask configuration.

    Examples:
      # Set all parameters
      orbfix cmd elevation-mask set --engine Tracking --mask 45

    # Raw payload
      orbfix cmd elevation-mask set --payload 01002D
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
        if len(payload_bytes) != 4:
            typer.secho(f"Warning: Payload is {len(payload_bytes)} bytes (expected 4)", fg="yellow")
    else:
        # All parameters required for SET
        if not all([engine, mask]):
            typer.secho("Error: All parameters required: --threshold --startupsync", fg="red")
            raise typer.Exit(code=1)

        # System mapping
        engine_map = {
            "tracking": 0x00,
            "pvt": 0x01,
            "all": 0x02,
        }

        # Validate bitfield
        engine_lower = engine.lower()
        if engine_lower not in engine_map:
            typer.secho("Error: selector must be Tracking, PVT, or all", fg="red")
            raise typer.Exit(code=1)

        engine_byte = engine_map[engine_lower]

        # Validate -90..90
        try:
            mask_value = int(mask)
            if mask_value < -90 or mask_value > 90:
                raise ValueError
        except ValueError:
            typer.secho("Angle must be between -90 and 90", fg="red")
            raise typer.Exit(code=1)

        # Convert to 1 bytes signed
        mask_bytes = mask_value.to_bytes(1, "big", signed=True)

        # Build final payload (2 bytes)
        payload_bytes = bytes([engine_byte]) + mask_bytes

        typer.secho("\nElevation Mask configuration:", fg="cyan", bold=True)
        typer.secho(f"  Engine: {engine}", fg="green")
        typer.secho(f"  Mask: {mask_value}", fg="green")
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
def get_elevation_mask(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current Elevation Mask configuration."""
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
