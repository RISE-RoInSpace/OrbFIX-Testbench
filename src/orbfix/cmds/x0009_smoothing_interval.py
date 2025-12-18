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

app = typer.Typer(help="Get or set the smoothing interval.")

CMD_ID = 0x0009
DEFAULT_SYSID = "0x6A"


# Parser for responses to this command
@register(CMD_ID)
def _parse_smoothing_interval(decoded):
    """
    Command 0x0009: Smoothing interval (Get/Set)
    Payload:
      - Byte offset  0: X4     - Bitfield of the supported satellite signals.
      - Byte offset  4: U2[26] - Interval in seconds, from 1 to 1000 seconds;
                                 If value is 0, then measurements are not smoothed.
      - Byte offset 56: U2[26] - Alignment in seconds, measurements taken in the
                                 first (Alignment + 10 seconds) will be discarded.
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 108:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    # Read first 4 bytes as the satellite bitfield (32 bits = satellites 0-31)
    # Big-endian interpretation per protocol standard
    bitfield = int.from_bytes(pl[:4], byteorder="big")

    # Extract the smoothing interval for each signal type
    intervals_bytes = pl[4:56]
    intervals_arr = [
        int.from_bytes(intervals_bytes[i : i + 2], byteorder="big")
        for i in range(0, 52, 2)
    ]

    # Extract the alignment for each signal type
    alignments_bytes = pl[56:108]
    alignments_arr = [
        int.from_bytes(alignments_bytes[i : i + 2], byteorder="big")
        for i in range(0, 52, 2)
    ]

    # Decode which satellite IDs are enabled (bit N set → satellite N tracked)
    enabled_sigs = [i for i in range(32) if (bitfield >> i) & 1]

    # Signal type names per bit position
    signal_map = {
        0: "GPSL1CA",
        1: "GPSL2PY",
        2: "GPSL2C",
        3: "GPSL5",
        4: "GLOL1CA",
        5: "GLOL2P",
        6: "GLOL2CA",
        7: "GLOL3",
        8: "GALL1BC",
        9: "GALE6BC",
        10: "GALE5a",
        11: "GALE5b",
        12: "GALE5",
        13: "GEOL1",
        14: "GEOL5",
        15: "BDSB1I",
        16: "BDSB2I",
        17: "BDSB3I",
        18: "BDSB1C",
        19: "BDSB2a",
        20: "BDSB2b",
        21: "QZSL1CA",
        22: "QZSL2C",
        23: "QZSL5",
        24: "QZSL1CB",
        25: "NAVICL5",
    }

    if enabled_sigs:
        sig_list = ", ".join(str(s) for s in enabled_sigs)
        result = f"Smoothing intervals: {len(enabled_sigs)} signals enabled\n"
        result += f"  Signals IDs: {sig_list};\n"
        result += f"  [index] signal_type: interval_val s - alignment_val s\n"
        for i in range(26):
            sig_name = signal_map.get(i, f"Signal_{i}")
            interval_val = intervals_arr[i]
            alignment_val = alignments_arr[i]
            result += f"  [{i:5d}] {sig_name:11}: {interval_val:12d} s - {alignment_val:13d} s\n"

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
            f"Smoothing intervals: No signals enabled (bitfield=0x{bitfield:08X})",
            {
                "signals_count": 0,
                "signals_ids": [],
                "bitfield_hex": f"0x{bitfield:08X}",
            },
        )


@app.command("set")
def set_smoothing_interval(
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
    default: bool = typer.Option(
        None,
        "--default",
        "-d",
        help="Default configuration (overrides other options) ",
        is_flag=True,
    ),
    default_interval: int = typer.Option(
        None,
        "--default_int",
        "-di",
        help="Default intervals (s) for all signals (0)",
    ),
    default_alignment: int = typer.Option(
        None,
        "--default_alg",
        "-da",
        help="Default alignments (s) for all signals (0)",
    ),
    signal_interval: list[str] = typer.Option(
        None,
        "--signal_int",
        "-si",
        help="Set interval per signal: 'GPSL1CA=10' or '0=10'",
    ),
    signal_alignment: list[str] = typer.Option(
        None,
        "--signal_alg",
        "-sa",
        help="Set alignment per signal: 'GPSL1CA=1' or '0=1'",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Set interval/alignment values for GNSS signals.

    Examples:
        # Set all signals'intervals to 10 seconds and aligments to 2 seconds
        orbfix cmd smoothing-interval set --default_int 10 --default_alg 2

        # Set specific signals by name
        orbfix cmd smoothing-interval set --signal_int GPSL1CA=10 --signal_alg GPSL1CA=5

        # Set by index
        orbfix cmd smoothing_interval set --signal_int 15=20 --signal_alg 10=2

        # Mix of approaches
        orbfix cmd smoothing_interval set -di 25 -da 12 -si 12=10 -sa 15=2
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
        if len(payload_bytes) != 108:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 108 for smoothing interval)",
                fg="yellow",
            )
    else:
        # Build from user-friendly options
        signal_map = {
            0: "GPSL1CA",
            1: "GPSL2PY",
            2: "GPSL2C",
            3: "GPSL5",
            4: "GLOL1CA",
            5: "GLOL2P",
            6: "GLOL2CA",
            7: "GLOL3",
            8: "GALL1BC",
            9: "GALE6BC",
            10: "GALE5a",
            11: "GALE5b",
            12: "GALE5",
            13: "GEOL1",
            14: "GEOL5",
            15: "BDSB1I",
            16: "BDSB2I",
            17: "BDSB3I",
            18: "BDSB1C",
            19: "BDSB2a",
            20: "BDSB2b",
            21: "QZSL1CA",
            22: "QZSL2C",
            23: "QZSL5",
            24: "QZSL1CB",
            25: "NAVICL5",
        }

        # Reverse map for name lookup
        name_to_index = {name: idx for idx, name in signal_map.items()}

        # Initialize bitfield
        bitfield = int.from_bytes(b"\x00\x00\x00\x00", byteorder="big")
        intervals = [0] * 26
        alignments = [0] * 26

        if default is True:
            intervals[name_to_index["GPSL1CA"]] = 30
            bitfield |= 1 << (name_to_index["GPSL1CA"])
            intervals[name_to_index["GPSL2PY"]] = 30
            bitfield |= 1 << (name_to_index["GPSL2PY"])
            intervals[name_to_index["GPSL2C"]] = 30
            bitfield |= 1 << (name_to_index["GPSL2C"])
            intervals[name_to_index["GPSL5"]] = 30
            bitfield |= 1 << (name_to_index["GPSL5"])
            intervals[name_to_index["GALL1BC"]] = 30
            bitfield |= 1 << (name_to_index["GALL1BC"])
            intervals[name_to_index["GALE5a"]] = 30
            bitfield |= 1 << (name_to_index["GALE5a"])
            intervals[name_to_index["GALE5b"]] = 30
            bitfield |= 1 << (name_to_index["GALE5b"])
            intervals[name_to_index["GALE5"]] = 30
            bitfield |= 1 << (name_to_index["GALE5"])

        # Initialize all intervals to default
        if default_interval is not None:
            if not 0 <= default_interval <= 1000:
                typer.secho("Error: Default interval must be 0 - 1000 s", fg="red")
                raise typer.Exit(code=1)
            intervals = [default_interval] * 26
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize all alignments to default or 0
        if default_alignment is not None:
            if not 0 <= default_alignment <= 1000:
                typer.secho(
                    "Error: Default alignments must be 0 - default_interval s", fg="red"
                )
                raise typer.Exit(code=1)
            alignments = [default_alignment] * 26
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")
        # Apply per-signal overrides for interval
        if signal_interval:
            for spec in signal_interval:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    interval_val = int(val_str.strip())

                    if not 0 <= interval_val <= 1000:
                        typer.secho(
                            f"Error: Interval for '{key}' must be 0-1000 s (got {interval_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 25:
                            intervals[idx] = interval_val
                            bitfield |= 1 << (idx)
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-25)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        intervals[idx] = interval_val
                        bitfield |= 1 << (idx)
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal threshold spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Apply per-signal overrides for alignment
        if signal_alignment:
            for spec in signal_alignment:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    alignment_val = int(val_str.strip())

                    if not 0 <= alignment_val <= 1000:
                        typer.secho(
                            f"Error: Alignment for '{key}' must be 0-1000 s (got {alignment_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 25:
                            alignments[idx] = alignment_val
                            bitfield |= 1 << (idx)
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        alignments[idx] = alignment_val
                        bitfield |= 1 << (idx)
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal threshold spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Convert to bytes
        payload_intervals = b"".join(x.to_bytes(2, byteorder="big") for x in intervals)
        payload_alignments = b"".join(
            x.to_bytes(2, byteorder="big") for x in alignments
        )
        payload_bytes = (
            bitfield.to_bytes(4, "big") + payload_intervals + payload_alignments
        )

        typer.secho("Smoothing interval - signals configuration:", fg="cyan", bold=True)
        for idx in range(26):
            sig_name = signal_map.get(idx, f"Signal_{idx}")
            sig_track_val = (bitfield >> idx) & 1
            typer.secho(
                f"  [{idx:2d}] {sig_name:12s}: {sig_track_val:2d}",
                fg="green",
            )
        typer.echo()

        # Show sent intervals
        typer.secho("\nSmoothing intervals:", fg="cyan", bold=True)
        changed = [i for i in range(26) if intervals[i] != (default_interval or 0)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {intervals[idx]:2d} s",
                    fg="green",
                )
        if default_interval is not None:
            typer.secho(f"  All other signals: {default_interval} s", fg="white")
        typer.echo()

        # Show sent alignments
        typer.secho("\nAlignments:", fg="cyan", bold=True)
        changed = [i for i in range(26) if alignments[i] != (default_alignment or 0)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {alignments[idx]:2d} s",
                    fg="green",
                )
        if default_alignment is not None:
            typer.secho(f"  All other signals: {default_alignment} s", fg="white")
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
def get_smoothing_interval(
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
