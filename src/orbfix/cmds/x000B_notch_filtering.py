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

app = typer.Typer(help="Get or set the Notch filter parameters")

CMD_ID = 0x000B
DEFAULT_SYSID = "0x6A"


@register(CMD_ID)
def _parse_notch_filtering(decoded):
    """
    Command 0x000B: Notch filtering (Get/Set)
    Payload:
      - Byte offset 0: U1 - Mode:   0x00 - Auto
                                    0x01 - Off
                                    0x02 - Manual
      - Byte offset 1: F4 - CenterFreq: 1100.000 .. 1700.000 MHz
      - Byte offset 5: U2 - Bandwidth:  30 .. 1600 KHz
    """

    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 7:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    import struct

    pl: bytes = getattr(decoded, "payload", b"") or b""

    mode_val = pl[0]  # 1 byte
    centerfreq_val = struct.unpack(">f", pl[1:5])[0]  # 4-byte float, big-endian
    bandwidth_val = int.from_bytes(pl[5:7], "big")  # 2 bytes

    # modes
    mode_map = {
        0: "auto",
        1: "off",
        2: "manual",
    }

    result = f"Notch filtering:\n"
    result += f"    Mode:        {mode_val:2d}:{mode_map.get(mode_val, f"Mode_{mode_val}"):12s}\n"
    result += f"    CenterFreq:   {centerfreq_val:.3f} [Mhz]\n"
    result += f"    Bandwidth:    {bandwidth_val} [Hz]"

    return (
        result,
        {
            "mode": f"{mode_val}",
            "centerfreq": f"{centerfreq_val}",
            "bandwidth": f"{bandwidth_val}",
        },
    )


@app.command("set")
def set_notch_filtering(
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
    default_filter: bool = typer.Option(
        None,
        "--default_filter",
        "-df",
        help="Set default values for notch filtering",
        is_flag=True,
    ),
    mode: str = typer.Option(
        None,
        "--mode",
        "-m",
        help="Set a value for the filtering mode",
    ),
    centerfreq: float = typer.Option(
        None,
        "--centerfreq",
        "-cf",
        help="Set a value for the center frequency",
    ),
    bandwidth: int = typer.Option(
        None,
        "--bandwidth",
        "-b",
        help="Set a value for the bandwidth",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Notch filtering.

    Examples:
        # Set default values
        orbfix cmd notch-filtering set --default_filter
        orbfix cmd notch-filtering set -df

        # Set certain values
        orbfix cmd notch-filtering set --mode off --centerfreq 1254.234 --bandwidth 56
        orbfix cmd notch-filtering set -m auto -cf 1337.67 -b 67
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
        if len(payload_bytes) != 7:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 7 for notch filtering)",
                fg="yellow",
            )
    else:
        # modes
        mode_map = {
            0: "auto",
            1: "off",
            2: "manual",
        }

        # Reverse map for name lookup
        mode_name_to_index = {name: idx for idx, name in mode_map.items()}

        mode_val = 0
        centerfreq_val = 0.0
        bandwidth_val = 0

        if default_filter is True:
            # Set default values for notch filtering
            interval_val = mode_name_to_index["auto"]
            centerfreq_val = 1100.0
            bandwidth_val = 30

        if mode is not None:
            # Set mode
            if mode not in mode_name_to_index:
                typer.secho(f"Error: Unknown mode name '{mode}'", fg="red")
                typer.secho(
                    f"Valid names: {', '.join(sorted(mode_name_to_index.keys()))}",
                    fg="yellow",
                )
                raise typer.Exit(code=1)
            mode_val = mode_name_to_index[mode]

        if centerfreq is not None:
            # Set center frequency
            if not 1100.0 <= centerfreq <= 1700.0:
                typer.secho(
                    f"Error: Center frequency value must be  1100.0 .. 1700.0 MHz",
                    fg="red",
                )
                raise typer.Exit(code=1)
            centerfreq_val = centerfreq

        if bandwidth is not None:
            # Set bandwidth value
            if not 30 <= bandwidth <= 1600:
                typer.secho(f"Error: Bandwidth value must be 30 .. 1600 KHz", fg="red")
                raise typer.Exit(code=1)
            bandwidth_val = bandwidth

        import struct

        payload_bytes = struct.pack(
            ">B" "f" "H",
            mode_val,
            centerfreq_val,
            bandwidth_val,
        )

        # Show what we're sending
        typer.secho(f"Notch filtering:\n", fg="cyan", bold=True)
        typer.secho(
            f"   mode:            {mode_val:2d}:{mode_map.get(mode_val, f"Mode_{mode_val}"):12s}"
        )
        typer.secho(f"   Center Frequency: {centerfreq_val:.3f} [MHz]")
        typer.secho(f"   Bandwidth:        {bandwidth_val} [KHz]")
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
def get_pps_parameters(
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
    """Get current Notch filtering configuration."""
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
