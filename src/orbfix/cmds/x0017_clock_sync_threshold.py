from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Request OrbFIX firmware/version info.")

CMD_ID = 0x0017
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_clock_sync(decoded):
    """
    Command 0x0014: Clock Sync Threshold (Get/Set)
    Payload: 2 bytes
      - Byte 0 (U1): Threshold
      - Byte 1 (U1): StartupSync
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 2:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    threshold = pl[0]
    startupSync = pl[1]

    # Satellite mapping
    threshold_map = {
        0x00: "ClockSteering",
        0x01: "usec500",
        0x02: "msec1",
        0x03: "msec2",
        0x04: "msec3",
        0x05: "msec4",
        0x06: "msec5",
    }

    startup_map = {
        0x00: "off",
        0x01: "on"
    }

    threshold_str = threshold_map.get(threshold, f"Unknown(0x{threshold:02X})")
    startup_str = startup_map.get(startupSync,f"Unknown(0x{startupSync:02X})")

    result = "Clock Sync Threshold:\n"
    result += f"  Threshold: {threshold_str}\n"
    result += f"  StartupSync: {startup_str}\n"
    return (
        result,
        {
            "threshold": threshold_str,
            "threshold_value": threshold,
            "startupSync": startup_str,
            "startupSync_value": startupSync,
        }
    )

@app.command("set")
def set_clock_sync_threshold(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    threshold: str = typer.Option(None, "--threshold", "-t", help="Threshold : ClockSteering, Usec500, Msec1, Msec2, Msec3, Msec4, Msec5"),
    startupSync: str = typer.Option(None, "--startupsync", "-s", help="Startup Sync: Off, On"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Clock Sync Threshold configuration.

    Examples:
      # Set all parameters
      orbfix cmd clock-sync-threshold set --threshold Usec500 --stratupsync On

    # Raw payload
      orbfix cmd clock-sync-threshold set --payload 0101
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
        if not all([threshold, startupSync]):
            typer.secho("Error: All parameters required: --threshold --startupsync", fg="red")
            raise typer.Exit(code=1)

        # System mapping
        threshold_map = {
            "clocksteering": 0x00,
            "usec500": 0x01,
            "msec1": 0x02,
            "msec2": 0x03,
            "msec3": 0x04,
            "msec4": 0x05,
            "msec5": 0x06,
        }
        startupSync_map = {
            "off": 0x00,
            "on": 0x01
        }

        # Parse and validate
        threshold_lower = threshold.lower()
        if threshold_lower not in threshold_map:
            typer.secho(f"Error: Unknown threshold '{threshold}'", fg="red")
            typer.secho(f"Valid values: {', '.join(threshold_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        threshold_byte = threshold_map[threshold_lower]

        startupSync_lower = startupSync.lower()
        if startupSync_lower not in startupSync_map:
            typer.secho(f"Error: Unknown startup sync '{startupSync}'", fg="red")
            typer.secho(f"Valid values: {', '.join(startupSync_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        startup_byte = startupSync_map[startupSync_lower]

        payload_bytes = bytes([threshold_byte, startup_byte])

        # Show configuration
        typer.secho("\nClock Sync Threshold Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Threshold: {threshold}", fg="green")
        typer.secho(f"  StartupSync: {startupSync}", fg="green")
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
    """Get current Clock Sync Threshold configuration."""
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
