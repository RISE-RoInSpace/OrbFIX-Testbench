from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the SBAS correction details in the PVT computation.")

CMD_ID = 0x0014
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_sbas_corrections(decoded):
    """
    Command 0x0014: SBAS Corrections (Get/Set)
    Payload: 4 bytes
      - Byte 0 (U1): Satellite
      - Byte 1 (U1): SISMode
      - Byte 2 (U1): NavMode
      - Byte 3 (U1): DO229Version
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 4:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    satellite = pl[0]
    sis_mode = pl[1]
    nav_mode = pl[2]
    do229_version = pl[3]

    # Satellite mapping
    satellite_map = {
        0x00: "Auto",
        0x01: "EGNOS",
        0x02: "WAAS",
        0x03: "MSAS",
        0x04: "GAGAN",
        0x05: "SDCM",
        0x06: "S120",
        # 0x07-0x2C: Reserved
        0x2D: "S158",
    }

    # SISMode mapping
    sis_mode_map = {
        0x00: "Test",
        0x01: "Operational",
    }

    # NavMode mapping
    nav_mode_map = {
        0x00: "EnRoute",
        0x01: "PrecApp",
        0x02: "MixedSystems",
    }

    # DO229Version mapping
    do229_version_map = {
        0x00: "Auto",
        0x01: "DO229C",
    }

    satellite_str = satellite_map.get(satellite, f"Unknown(0x{satellite:02X})")
    sis_mode_str = sis_mode_map.get(sis_mode, f"Unknown(0x{sis_mode:02X})")
    nav_mode_str = nav_mode_map.get(nav_mode, f"Unknown(0x{nav_mode:02X})")
    do229_str = do229_version_map.get(do229_version, f"Unknown(0x{do229_version:02X})")

    result = "SBAS Corrections:\n"
    result += f"  Satellite: {satellite_str}\n"
    result += f"  SIS Mode: {sis_mode_str}\n"
    result += f"  Nav Mode: {nav_mode_str}\n"
    result += f"  DO-229 Version: {do229_str}"

    return (
        result,
        {
            "satellite": satellite_str,
            "satellite_value": satellite,
            "sis_mode": sis_mode_str,
            "sis_mode_value": sis_mode,
            "nav_mode": nav_mode_str,
            "nav_mode_value": nav_mode,
            "do229_version": do229_str,
            "do229_version_value": do229_version,
        }
    )

@app.command("set")
def set_sbas_corrections(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    satellite: str = typer.Option(None, "--satellite", "-s", help="Satellite: auto, egnos, waas, msas, gagan, sdcm, s120, s158"),
    sis_mode: str = typer.Option(None, "--sis-mode", help="SIS Mode: test, operational"),
    nav_mode: str = typer.Option(None, "--nav-mode", "-n", help="Nav Mode: enroute, precapp, mixedsystems"),
    do229_version: str = typer.Option(None, "--do229", "-d", help="DO-229 Version: auto, do229c"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set SBAS corrections configuration.

    Examples:
      # Set all parameters
      orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 auto

      # Set specific parameters (all required)
      orbfix cmd sbas-corrections set -s egnos --sis-mode test -n enroute -d auto

    # Raw payload
      orbfix cmd sbas-corrections set --payload 01000100
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
        if not all([satellite, sis_mode, nav_mode, do229_version]):
            typer.secho("Error: All parameters required: --satellite, --sis-mode, --nav-mode, --do229", fg="red")
            raise typer.Exit(code=1)

        # Satellite mapping
        satellite_map = {
            "auto": 0x00,
            "egnos": 0x01,
            "waas": 0x02,
            "msas": 0x03,
            "gagan": 0x04,
            "sdcm": 0x05,
            "s120": 0x06,
            "s158": 0x2D,
        }

        # SISMode mapping
        sis_mode_map = {
            "test": 0x00,
            "operational": 0x01,
        }

        # NavMode mapping
        nav_mode_map = {
            "enroute": 0x00,
            "precapp": 0x01,
            "mixedsystems": 0x02,
        }

        # DO229Version mapping
        do229_version_map = {
            "auto": 0x00,
            "do229c": 0x01,
        }

        # Parse and validate
        sat_lower = satellite.lower()
        if sat_lower not in satellite_map:
            typer.secho(f"Error: Unknown satellite '{satellite}'", fg="red")
            typer.secho(f"Valid values: {', '.join(satellite_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        satellite_byte = satellite_map[sat_lower]

        sis_lower = sis_mode.lower()
        if sis_lower not in sis_mode_map:
            typer.secho(f"Error: Unknown SIS mode '{sis_mode}'", fg="red")
            typer.secho(f"Valid values: {', '.join(sis_mode_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        sis_mode_byte = sis_mode_map[sis_lower]

        nav_lower = nav_mode.lower()
        if nav_lower not in nav_mode_map:
            typer.secho(f"Error: Unknown nav mode '{nav_mode}'", fg="red")
            typer.secho(f"Valid values: {', '.join(nav_mode_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        nav_mode_byte = nav_mode_map[nav_lower]

        do229_lower = do229_version.lower()
        if do229_lower not in do229_version_map:
            typer.secho(f"Error: Unknown DO-229 version '{do229_version}'", fg="red")
            typer.secho(f"Valid values: {', '.join(do229_version_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        do229_byte = do229_version_map[do229_lower]

        payload_bytes = bytes([satellite_byte, sis_mode_byte, nav_mode_byte, do229_byte])

        # Show configuration
        typer.secho("\nSBAS Corrections Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Satellite: {satellite}", fg="green")
        typer.secho(f"  SIS Mode: {sis_mode}", fg="green")
        typer.secho(f"  Nav Mode: {nav_mode}", fg="green")
        typer.secho(f"  DO-229 Version: {do229_version}", fg="green")
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
def get_sbas_corrections(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current SBAS corrections configuration."""
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
