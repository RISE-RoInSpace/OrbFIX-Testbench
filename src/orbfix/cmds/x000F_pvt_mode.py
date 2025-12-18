from __future__ import annotations

import typer

from ..common.io_utils import parse_one_byte_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Set OrbFIX PVT mode (simple/normal).")

DEFAULT_SYSID = "0x6A"

CMD_ID = 0x000F

# Parser for responses to this command
@register(CMD_ID)
def _parse_PVTMode(decoded):
    """
    Command 0x000F: PVT Mode (Get/Set)
    Payload: 3 bytes
      - Byte 0 (U1): Mode
          0 = static
          1 = rover
      - Byte 1 (X1): RoverMode bitfield (only used when Mode=1)
          Bit 0: RTKFixed
          Bit 1: RTKFloat
          Bit 2: DGNSS
          Bit 3: SBAS
          Bit 4: Standalone
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 2:
        return (
            f"Payload too short: {len(pl)} bytes (expected 2)",
            {"error": "short_payload", "received_bytes": len(pl)}
        )

    mode = pl[0]
    rover_mode_bitfield = pl[1]

    # Mode interpretation
    mode_str = "static" if mode == 0 else "rover" if mode == 1 else f"unknown({mode})"

    result = f"PVT Mode: {mode_str}\n"

    # If rover mode, decode the bitfield
    if mode == 1:
        rover_features = {
            0: "RTKFixed",
            1: "RTKFloat",
            2: "DGNSS",
            3: "SBAS",
            4: "Standalone",
        }

        enabled_features = []
        for bit_pos, feature_name in rover_features.items():
            if (rover_mode_bitfield >> bit_pos) & 1:
                enabled_features.append(feature_name)

        if enabled_features:
            result += f"  Rover mode features enabled:\n"
            for feature in enabled_features:
                result += f"    • {feature}\n"
            result = result.rstrip("\n")
        else:
            result += f"  Rover mode: no features enabled (bitfield=0x{rover_mode_bitfield:02X})"
    elif mode == 0:
        # Static mode - bitfield ignored
        if rover_mode_bitfield != 0:
            result += f"  (RoverMode bitfield=0x{rover_mode_bitfield:02X}, ignored in static mode)"

    return (
        result,
        {
            "mode": mode_str,
            "mode_value": mode,
            "rover_mode_bitfield": f"0x{rover_mode_bitfield:02X}",
            "rover_features_enabled": enabled_features if mode == 1 else None,
        }
    )

@app.command("set")
def set_pvt_mode(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    mode: str = typer.Option(None, "--mode", "-m", help="PVT mode: 'static' or 'rover'"),
    rover_features: list[str] = typer.Option(None, "--feature", "-f", help="Enable rover feature: 'SBAS', 'RTKFloat', etc."),
    rover_bitfield: str = typer.Option(None, "--rover-bitfield", help="Raw rover mode bitfield (hex, e.g., '0x15')"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set PVT mode (static or rover) and rover features.

    Examples:
      # Set static mode
      orbfix cmd pvt-mode set --mode static

      # Set rover mode with features
      orbfix cmd pvt-mode set --mode rover --feature RTKFixed --feature DGNSS

      # Set rover mode with bitfield
      orbfix cmd pvt-mode set --mode rover --rover-bitfield 0x15

      # Set rover mode, all features enabled
      orbfix cmd pvt-mode set -m rover -f RTKFixed -f RTKFloat -f DGNSS -f SBAS -f Standalone
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
        # User provided raw hex payload
        payload_bytes = parse_payload_spec(payload)
        if len(payload_bytes) != 2:
            typer.secho(f"Warning: Payload is {len(payload_bytes)} bytes (expected 2 for PVT mode)", fg="yellow")
    else:
        # Build from user-friendly options
        if mode is None:
            typer.secho("Error: --mode is required (use 'static' or 'rover')", fg="red")
            raise typer.Exit(code=1)

        mode_lower = mode.lower()
        if mode_lower == "static":
            mode_byte = 0
            rover_mode_byte = 0x1F  # Ignored in static mode
        elif mode_lower == "rover":
            mode_byte = 1
            rover_feature_map = {
                "rtkfixed": 0,
                "rtkfloat": 1,
                "dgnss": 2,
                "sbas": 3,
                "standalone":4,
            }

            if rover_bitfield is not None:
                # User provided raw bitfield
                try:
                    if rover_bitfield.startswith(("0x", "0X")):
                        rover_mode_byte = int(rover_bitfield, 16)
                    else:
                        rover_mode_byte = int(rover_bitfield, 10)

                    if not 0 <= rover_mode_byte <= 255:
                        typer.secho(f"Error: Rover bitfield must be 0-255 (got {rover_mode_byte})", fg="red")
                        raise typer.Exit(code=1)
                except ValueError:
                    typer.secho(f"Error: Invalid rover bitfield '{rover_bitfield}'", fg="red")
                    raise typer.Exit(code=1)
            elif rover_features:
                # Build bitfield from feature names
                rover_mode_byte = 0
                for feature in rover_features:
                    feature_lower = feature.lower()
                    if feature_lower in rover_feature_map:
                        bit_pos = rover_feature_map[feature_lower]
                        rover_mode_byte |= (1 << bit_pos)
                    else:
                        typer.secho(f"Error: Unknown rover feature '{feature}'", fg="red")
                        typer.secho(f"Valid features: {', '.join(rover_feature_map.keys())}", fg="yellow")
                        raise typer.Exit(code=1)
            else:
                # Rover mode with no features enabled
                rover_mode_byte = 0x1F
        else:
            typer.secho(f"Error: Invalid mode '{mode}'. Use 'static' or 'rover'", fg="red")
            raise typer.Exit(code=1)

        payload_bytes = bytes([mode_byte, rover_mode_byte])

        # Show what we're sending
        typer.secho("\nPVT Mode Configuration:", fg="cyan", bold=True)
        if mode_byte == 0:
            typer.secho("  Mode: static", fg="green")
        else:
            typer.secho("  Mode: rover", fg="green")
            if rover_mode_byte > 0:
                typer.secho(f"  Rover mode bitfield: 0x{rover_mode_byte:02X}", fg="white")
                enabled = [name for name, bit in rover_feature_map.items() if (rover_mode_byte >> bit) & 1]
                if enabled:
                    typer.secho("  Enabled features:", fg="white")
                    for feature in enabled:
                        typer.secho(f"    • {feature}", fg="green")
            else:
                typer.secho("  Rover mode: no features enabled", fg="yellow")
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
def pvt_mode(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    auto: bool = typer.Option(False, help="Auto-detect USB device by VID/PID"),
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
