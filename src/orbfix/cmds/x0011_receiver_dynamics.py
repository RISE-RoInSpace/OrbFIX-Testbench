from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the type of receiver dynamics.")

CMD_ID = 0x0011
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_receiver_dynamics(decoded):
    """
    Command 0x0011: Receiver Dynamics (Get/Set)
    Payload: 2 bytes
      - Byte 0 (U1): Level
      - Byte 1 (U1): Motion
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 2:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    level = pl[0]
    motion = pl[1]

    # Level mapping
    level_map = {
        0x00: "Low",
        0x01: "Moderate",
        0x02: "High",
        0x03: "Max",
    }

    # Motion mapping
    motion_map = {
        0x00: "Static",
        0x01: "Quasistatic",
        0x02: "Pedestrian",
        0x03: "Automotive",
        0x04: "RaceCar",
        0x05: "HeavyMachinery",
        0x06: "UAV",
        0x07: "Unlimited",
    }

    level_str = level_map.get(level, f"Unknown(0x{level:02X})")
    motion_str = motion_map.get(motion, f"Unknown(0x{motion:02X})")

    result = "Receiver dynamics:\n"
    result += f"  Level: {level_str}\n"
    result += f"  Motion: {motion_str}\n"

    return (
        result,
        {
            "level": level_str,
            "level_value": level,
            "motion": motion_str,
            "motion_value": motion,
        }
    )

@app.command("set")
def set_receiver_dynamics(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    level: str = typer.Option(None, "--level", "-l", help="Level: Low, Moderate, High, Max"),
    motion: str = typer.Option(None, "--motion", "-m", help="Motion: Static, Quasistatic, Pedestrian, Automotive, RaceCar, HeavyMachinery, UAV, Unlimited"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set Receiver Dynamics configuration.

    Examples:
      # Set all parameters
      orbfix cmd receiver-dynamics set --level Low --motion Unlimited

    # Raw payload
      orbfix cmd receiver-dynamics set --payload 0205
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
        if not all([level, motion]):
            typer.secho("Error: All parameters required: --level, --motion", fg="red")
            raise typer.Exit(code=1)

        # Level mapping
        level_map = {
            "low":0x00,
            "moderate":0x01,
            "high":0x02,
            "max":0x03,
        }

        # Motion mapping
        motion_map = {
            "static":0x00,
            "quasistatic":0x01,
            "pedestrian":0x02,
            "automotive":0x03,
            "racecar":0x04,
            "heavymachinery":0x05,
            "uav":0x06,
            "unlimited":0x07,
        }

        # Parse and validate
        level_lower = level.lower()
        if level_lower not in level_map:
            typer.secho(f"Error: Unknown level '{level}'", fg="red")
            typer.secho(f"Valid values: {', '.join(level_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        level_byte = level_map[level_lower]

        motion_lower = motion.lower()
        if motion_lower not in motion_map:
            typer.secho(f"Error: Unknown motion '{motion}'", fg="red")
            typer.secho(f"Valid values: {', '.join(motion_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        motion_byte = motion_map[motion_lower]

        payload_bytes = bytes([level_byte, motion_byte])

        # Show configuration
        typer.secho("\nReceiver Dynamics Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Level: {level}", fg="green")
        typer.secho(f"  Motion: {motion}", fg="green")
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
def get_receiver_dynamics(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current Receiver Dynamics configuration."""
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
