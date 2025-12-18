from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec
from ..common.io_utils import parse_payload_spec
from ..transport.serial_rs422 import (
    find_usb_device,
    DEFAULT_BAUD,
    DEFAULT_READ_TIMEOUT_S,
)
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set which satellites are allowed to be tracked.")

CMD_ID = 0x0008
DEFAULT_SYSID = "0x6A"


# Parser for responses to this command
@register(CMD_ID)
def _parse_signal_tracking(decoded):
    """
    Command 0x0008: Signal Tracking (Get/Set)
    Payload: 4 bytes
      - Byte offset 0: X4 - Bitfield of the supported satellite signals

    Each bit represents whether a signal is allowed to be tracked by the receiver.
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 4:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    # Read first 4 bytes as the satellite signal bitfield (32 bits = satellites 0-31)
    # Big-endian interpretation per protocol standard
    bitfield = int.from_bytes(pl[:4], byteorder="big")

    # Decode which satellite signals are enabled (bit N set → signal N tracked)
    enabled_sigs = [i for i in range(32) if (bitfield >> i) & 1]

    # Build from user-friendly options
    signal_map = {
        0: "GPSL1CA",
        1: "GPSL1PY",
        2: "GPSL2PY",
        3: "GPSL2C",
        4: "GPSL5",
        5: "GLOL1CA",
        6: "GLOL2P",
        7: "GLOL2CA",
        8: "GLOL3",
        9: "GALL1BC",
        10: "GALE6BC",
        11: "GALE5a",
        12: "GALE5b",
        13: "GALE5",
        14: "GEOL1",
        15: "GEOL5",
        16: "BDSB1I",
        17: "BDSB2I",
        18: "BDSB3I",
        19: "BDSB1C",
        20: "BDSB2a",
        21: "BDSB2b",
        22: "QZSL1CA",
        23: "QZSL2C",
        24: "QZSL5",
        25: "QZSL1CB",
        26: "NAVICL5",
    }

    if enabled_sigs:
        result = f"Signal Tracking: {len(enabled_sigs)} signals enabled\n"
        result += "Tracked Signals:\n"
        for i in enabled_sigs:
            sig_name = signal_map.get(i, f"Signal_{i}")
            result += f"  [{i:2d}] {sig_name:12s}\n"

        result = result.rstrip("\n")
        return (
            result,
            {
                "signals_count": len(enabled_sigs),
                "signals_ids": enabled_sigs,
                "bitfield_hex": f"0x{bitfield:08X}",
            },
        )
    else:
        return (
            f"Signal Tracking: No satellites enabled (bitfield=0x{bitfield:08X})",
            {
                "signals_count": 0,
                "signals_ids": [],
                "bitfield_hex": f"0x{bitfield:08X}",
            },
        )


@app.command("set")
def set_signal_tracking(
    sysid: str = typer.Option(
        DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"
    ),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(
        DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"
    ),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly payload options
    default_signals: bool = typer.Option(
        None,
        "--default",
        "-d",
        help="Default signals enabled for tracking",
        is_flag=True,
    ),
    track_sig: list[str] = typer.Option(
        None,
        "--track_sig",
        "-ts",
        help="Set tracking for a signal: 'GPSL1CA=0' or '0=1'",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Set/Get tracking for GNSS signals

    Examples:
      # Set tracking for the default signals as defined in config
      orbfix cmd signal_tracking set --default

      # Set specific signals by name
      orbfix cmd signal_tracking set --default --track_sig GPSL1CA=1 --signal BDSB1I=0

      # Set by index
      orbfix cmd signal_tracking set --default --signal 0=1 --signal 15=0

      # Mix of approaches
      orbfix cmd signal_tracking set -d -ts GPSL5=1 -ts GLOL1CA=1 -ts 21=0
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

    # Build payload
    if payload:
        # User provided raw hex payload
        payload_bytes = parse_payload_spec(payload)
        if len(payload_bytes) != 4:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 4 for signal tracking)",
                fg="yellow",
            )
    else:
        # Build from user-friendly options
        signal_map = {
            0: "GPSL1CA",
            1: "GPSL1PY",
            2: "GPSL2PY",
            3: "GPSL2C",
            4: "GPSL5",
            5: "GLOL1CA",
            6: "GLOL2P",
            7: "GLOL2CA",
            8: "GLOL3",
            9: "GALL1BC",
            10: "GALE6BC",
            11: "GALE5a",
            12: "GALE5b",
            13: "GALE5",
            14: "GEOL1",
            15: "GEOL5",
            16: "BDSB1I",
            17: "BDSB2I",
            18: "BDSB3I",
            19: "BDSB1C",
            20: "BDSB2a",
            21: "BDSB2b",
            22: "QZSL1CA",
            23: "QZSL2C",
            24: "QZSL5",
            25: "QZSL1CB",
            26: "NAVICL5",
        }

        # Reverse map for name lookup
        name_to_index = {name: idx for idx, name in signal_map.items()}

        # Initialize all thresholds to default or 0
        bitfield = int.from_bytes(b"\x00\x00\x00\x00", byteorder="big")
        if default_signals is True:
            bitfield |= 1 << (name_to_index["GPSL1CA"])
            bitfield |= 1 << (name_to_index["GPSL1PY"])
            bitfield |= 1 << (name_to_index["GPSL2PY"])
            bitfield |= 1 << (name_to_index["GPSL2C"])
            bitfield |= 1 << (name_to_index["GPSL5"])
            bitfield |= 1 << (name_to_index["GALL1BC"])
            bitfield |= 1 << (name_to_index["GALE6BC"])
            bitfield |= 1 << (name_to_index["GALE5a"])
            bitfield |= 1 << (name_to_index["GALE5b"])
            bitfield |= 1 << (name_to_index["GALE5"])

        # Apply per-signal overrides
        if track_sig:
            for spec in track_sig:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    track_val = int(val_str.strip())

                    if not 0 <= track_val <= 1:
                        typer.secho(
                            f"Error: Value of signal tracking for '{key}' must be 0(do not track) or 1(track) (got {track_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            bitfield |= track_val << (idx)
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        bitfield |= track_val << (idx)
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal track spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Convert to bytes
        payload_bytes = bitfield.to_bytes(4, byteorder="big")

        # Show what we're sending
        typer.secho("\nSignal Tracking Configuration:", fg="cyan", bold=True)
        for idx in range(27):
            sig_name = signal_map.get(idx, f"Signal_{idx}")
            sig_track_val = (bitfield >> idx) & 1
            typer.secho(
                f"  [{idx:2d}] {sig_name:12s}: {sig_track_val:2d}",
                fg="green",
            )
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
def get_signal_tracking(
    sysid: str = typer.Option(
        DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"
    ),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(
        DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"
    ),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
    from ..transport.serial_rs422 import find_usb_device
    from pathlib import Path

    saved = get_default_port()
    resolved_port = port or (saved if saved and Path(saved).exists() else None)
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
