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

app = typer.Typer(help="Get or set the parameters of the xPPS output")

CMD_ID = 0x0018
DEFAULT_SYSID = "0x6A"


@register(CMD_ID)
def _parse_pps_parameters(decoded):
    """
    Command 0x0018: PPS parameters (Get/Set)
    Payload:
      - Byte offset  0: U1 - Interval:  0x00 - Off
                                        0x01 - Msec10
                                        0x02 - Msec20
                                        0x03 - Msec50
                                        0x04 - Msec100.
                                        0x05 - Msec200.
                                        0x06 - Msec250.
                                        0x07 - Msec500.
                                        0x08 - Sec1.
                                        0x09 - Sec2.
                                        0x0A - Sec4.
                                        0x0B - Sec5.
                                        0x0C - Sec10.
                                        0x0D - Sec30.
                                        0x0E - Sec60.
      - Byte offset 1: U1 - Polarity:   0x00 - Low2High
                                        0x01 - High2Low
      - Byte offset 2: F4 - Delay:      -1e6 .. 0.0 .. +1e6 [ns]
      - Byte offset 6: U1 - Timescale:  0x00 - GPS
                                        0x01 - Galileo
                                        0x02 - BeiDou
                                        0x03 - GLONASS
                                        0x04 - UTC
                                        0x05 - RxClock
      - Byte offset 7: U2 - MaxSyncAge: 0 .. 60 .. 3600 [s]
      - Byte offset 9: F4 - PulseWidth: 1e-6 .. 5.00 .. 1e3 [ms]
    """

    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 13:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    # interval_val = int.from_bytes(pl[0:0], byteorder="big")
    # polarity_val = int.from_bytes(pl[1:1], byteorder="big")
    # delay_val = float.from_bytes(pl[2:6], byteorder="big")
    # timescale_val = int.from_bytes(pl[6:6], byteorder="big")
    # maxsyncage_val = int.from_bytes(pl[7:9], byteorder="big")
    # pulsewidth_val = float.from_bytes(pl[9:], byteorder="big")

    import struct

    pl: bytes = getattr(decoded, "payload", b"") or b""

    interval_val = pl[0]  # 1 byte
    polarity_val = pl[1]  # 1 byte
    delay_val = struct.unpack(">f", pl[2:6])[0]  # 4-byte float, big-endian
    timescale_val = pl[6]  # 1 byte
    maxsyncage_val = int.from_bytes(pl[7:9], "big")  # 2 bytes
    pulsewidth_val = struct.unpack(">f", pl[9:13])[
        0
    ]  # 4-byte float (adjust if different!)

    # Timescales
    timescale_map = {
        0: "GPS",
        1: "Galileo",
        2: "BeiDou",
        3: "GLONASS",
        4: "UTC",
        5: "RxClock",
    }

    # Intervals
    interval_map = {
        0: "Off",
        1: "Msec10",
        2: "Msec20",
        3: "Msec50",
        4: "Msec100",
        5: "Msec200",
        6: "Msec250",
        7: "Msec500",
        8: "Sec1",
        9: "Sec2",
        10: "Sec4",
        11: "Sec5",
        12: "Sec10",
        13: "Sec30",
        14: "Sec60",
    }

    # Polarity
    polarity_map = {
        0: "Low2High",
        1: "High2Low",
    }

    result = f"PPS parameters:\n"
    result += f"    Interval:   {interval_val:2d}:{interval_map.get(interval_val, f"Interval_{interval_val}"):12s}\n"
    result += f"    Polarity:   {polarity_val:2d}:{polarity_map.get(polarity_val, f"Pol_{polarity_val}"):12s}\n"
    result += f"    Delay:      {delay_val} [ns]\n"
    result += f"    Timescale:  {timescale_val:2d}:{timescale_map.get(timescale_val, f"Timescale_{timescale_val}"):12s}\n"
    result += f"    MaxSyncAge: {maxsyncage_val} [s]\n"
    result += f"    PulseWidth: {pulsewidth_val} [ms]"

    return (
        result,
        {
            "interval": f"{interval_val}",
            "polarity": f"{polarity_val}",
            "delay": f"{delay_val}",
            "timescale": f"{timescale_val}",
            "maxsyncage": f"{maxsyncage_val}",
            "pulsewidth": f"{pulsewidth_val}",
        },
    )


@app.command("set")
def set_pps_parameters(
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
    default_pps: bool = typer.Option(
        None,
        "--default_pps",
        "-dpps",
        help="Set default values for pps parameters",
        is_flag=True,
    ),
    interval: str = typer.Option(
        None,
        "--interval",
        "-i",
        help="Set a value for the interval between pulses",
    ),
    polarity: str = typer.Option(
        None,
        "--polarity",
        "-p",
        help="Set a value for the polarity of the xPPS signal",
    ),
    delay: float = typer.Option(
        None,
        "--delay",
        "-d",
        help="Set a value for the overall signal delays in the system",
    ),
    timescale: str = typer.Option(
        None,
        "--timescale",
        "-ts",
        help="Set a value for the TimeScale",
    ),
    maxsyncage: int = typer.Option(
        None,
        "--maxsyncage",
        "-msc",
        help="Set a value for the MaxSyncAge",
    ),
    pulsewidth: float = typer.Option(
        None,
        "--pulsewidth",
        "-pw",
        help="Set a value for the PulseWidth",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    PPS parameters.

    Examples:
        # Set default values
        orbfix cmd pps-parameters set --default_pps
        orbfix cmd pps-parameters set -dpps

        # Set certain values
        orbfix cmd pps-parameters set --polarity 0 -- delay 10.23
        orbfix cmd pps-parameters set -ts GPS -pw 6.79 --interval sec4
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
        if len(payload_bytes) != 13:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 13 for pps values)",
                fg="yellow",
            )
    else:
        # Timescales
        timescale_map = {
            0: "GPS",
            1: "GALILEO",
            2: "BEIDOU",
            3: "GLONASS",
            4: "UTC",
            5: "RXCLOCK",
        }

        # Intervals
        interval_map = {
            0: "OFF",
            1: "MSEC10",
            2: "MSEC20",
            3: "MSEC50",
            4: "MSEC100",
            5: "MSEC200",
            6: "MSEC250",
            7: "MSEC500",
            8: "SEC1",
            9: "SEC2",
            10: "SEC4",
            11: "SEC5",
            12: "SEC10",
            13: "SEC30",
            14: "SEC60",
        }

        # Polarity
        polarity_map = {
            0: "LOW2HIGH",
            1: "HIGH2LOW",
        }

        # Reverse map for name lookup
        timescale_name_to_index = {name: idx for idx, name in timescale_map.items()}
        interval_name_to_index = {name: idx for idx, name in interval_map.items()}
        polarity_name_to_index = {name: idx for idx, name in polarity_map.items()}

        interval_val = 0
        polarity_val = 0
        delay_val = 0.0
        timescale_val = 0
        maxsyncage_val = 0
        pulsewidth_val = 1e-6

        if default_pps is True:
            # Set default values for PPS
            interval_val = interval_name_to_index["SEC1"]
            polarity_val = polarity_name_to_index["LOW2HIGH"]
            delay_val = 0.0
            timescale_val = timescale_name_to_index["GPS"]
            maxsyncage_val = 60
            pulsewidth_val = 5.0

        if interval is not None:
            # Set interval value
            if interval not in interval_name_to_index:
                typer.secho(f"Error: Unknown interval name '{interval}'", fg="red")
                typer.secho(
                    f"Valid names: {', '.join(sorted(interval_name_to_index.keys()))}",
                    fg="yellow",
                )
                raise typer.Exit(code=1)
            interval_val = interval_name_to_index[interval]

        if polarity is not None:
            # Set polarity value
            if polarity not in polarity_name_to_index:
                typer.secho(f"Error: Unknown polairty name '{polarity}'", fg="red")
                typer.secho(
                    f"Valid names: {', '.join(sorted(polarity_name_to_index.keys()))}",
                    fg="yellow",
                )
                raise typer.Exit(code=1)
            polarity_val = polarity_name_to_index[polarity]

        if delay is not None:
            # Set delay value
            if not -1e6 <= float(delay) <= 1e6:
                typer.secho(f"Error: Delay value must be  -1e6 .. 1e6", fg="red")
                raise typer.Exit(code=1)
            delay_val = float(delay)

        if timescale is not None:
            # Set timescale value
            if timescale not in timescale_name_to_index:
                typer.secho(f"Error: Unknown timescale name '{timescale}'", fg="red")
                typer.secho(
                    f"Valid names: {', '.join(sorted(timescale_name_to_index.keys()))}",
                    fg="yellow",
                )
                raise typer.Exit(code=1)
            timescale_val = timescale_name_to_index[timescale]

        if maxsyncage is not None:
            # Set maxsyncage value
            if not 0 <= maxsyncage <= 3600:
                typer.secho(f"Error: MaxSyncAge value must be 0 .. 3600", fg="red")
                raise typer.Exit(code=1)
            maxsyncage_val = maxsyncage

        if pulsewidth is not None:
            # Set pulsewidth value
            if not 1e-6 <= pulsewidth <= 1e3:
                typer.secho(f"Error: PulseWidth  value must be 1e-6 .. 1e3", fg="red")
                raise typer.Exit(code=1)
            pulsewidth_val = pulsewidth

        import struct

        payload_bytes = struct.pack(
            ">BB" "f" "B" "H" "f",
            interval_val,
            polarity_val,
            delay_val,
            timescale_val,
            maxsyncage_val,
            pulsewidth_val,
        )

        # Show what we're sending
        typer.secho(f"PPS parameters:\n", fg="cyan", bold=True)
        typer.secho(
            f"    Interval: {interval_val:2d}:{interval_map.get(interval_val, f"Interval_{interval_val}"):12s}\n"
        )
        typer.secho(
            f"    Polarity: {polarity_val:2d}:{polarity_map.get(polarity_val, f"Pol_{polarity_val}"):12s}\n"
        )
        typer.secho(f"        Delay: {delay_val} [ns]\n")
        typer.secho(
            f"    Timescale:{timescale_val:2d}:{timescale_map.get(timescale_val, f"Timescale_{timescale_val}"):12s}\n"
        )
        typer.secho(f"   MaxSyncAge: {maxsyncage_val} [s]\n")
        typer.secho(f"   PulseWidth: {pulsewidth_val} [ms]")
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
