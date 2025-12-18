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

CMD_ID = 0x0007
DEFAULT_SYSID = "0x6A"


def decode_enabled_sats(bitfield, start, end):
    return [(sid - start + 1) for sid in range(start, end + 1) if (bitfield >> sid) & 1]


@register(CMD_ID)
def _parse_satellite_usage(decoded):
    """
    Command 0x0013: Satellite tracking (Get/Set)
    Payload:
      - Byte offset  0: X4[7]     - Bitfield of the supported satellites.
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 28:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    bitfield = int.from_bytes(pl, byteorder="big")

    # Ranges for the satellite constelations
    sat_const_ranges = {
        "GPS": (0, 31),
        "GLONASS": (32, 61),
        "Galileo": (62, 97),
        "SBAS": (98, 136),
        "BeiDou": (137, 199),
        "QZSS": (200, 206),
    }

    # Codes for the satellite for each constelation
    sat_const_codes = {
        "G": "GPS",
        "R": "GLONASS",
        "E": "Galileo",
        "S": "SBAS",
        "C": "BeiDou",
        "J": "QZSS",
    }

    # Values for all satellites
    sat_vals = {
        "G": (1, 32),
        "R": (1, 30),
        "E": (1, 36),
        "S": (120, 158),
        "C": (1, 63),
        "J": (1, 7),
    }

    # Decode which satellites from each constelation are enabled
    enabled_sats = parse_bitfield(bitfield, sat_const_ranges, sat_vals, sat_const_codes)

    result = f"Satellite tracking: (bitfield=0x{bitfield:08X})"
    result += f"  Constelation:[IDs]\n"

    for constelation, sats in enabled_sats.items():
        if len(sats) > 0:
            sats_list = ", ".join(str(s) for s in sats)
            result += f"  {constelation:12}:[{sats_list}]\n"

    return (
        result,
        {
            "bitfield_hex": f"0x{bitfield:08X}",
        },
    )


def parse_bitfield(bitfield, sat_const_ranges, sat_vals, sat_const_codes):
    enabled_sats = {}

    for const, (start, end) in sat_const_ranges.items():
        sats = []

        const_code = next(k for k, v in sat_const_codes.items() if v == const)

        prn_start, _ = sat_vals[const_code]

        for i in range(start, end + 1):
            if (bitfield >> i) & 1:
                enabled_sat_num = prn_start + (i - start)
                sats.append(enabled_sat_num)
        enabled_sats[const] = sats

    return enabled_sats


@app.command("set")
def set_satellite_usage(
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
    default_sats: bool = typer.Option(
        None,
        "--default_sats",
        "-ds",
        help="Enable the default satellites",
        is_flag=True,
    ),
    constelation: list[str] = typer.Option(
        None,
        "--constelation",
        "-cstl",
        help="Select a certain constelation and enable all sats from it",
    ),
    satellite: list[str] = typer.Option(
        None,
        "--satellite",
        "-stl",
        help="Select a certain satellite from a constelation and enable it",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Satellite Tracking.

    Examples:
        # Enable default satellites
        orbfix cmd satellite-tracking set --default_sats
        orbfix cmd satellite-tracking set --ds

        # Enable a certain constelation
        orbfix cmd satellite-tracking set --constelation Galileo
        orbfix cmd satellite-tracking set -cstl GPS -cstl Galileo

        # Enable a certain satellite
        orbfix cmd satellite-tracking set --satellite G01
        orbfix cmd satellite-tracking set -stl G02 -stl J02

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
        if len(payload_bytes) != 28:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 28 for satellite bitfield)",
                fg="yellow",
            )
    else:
        # Ranges for the satellite constelations
        sat_const_ranges = {
            "GPS": (0, 31),
            "GLONASS": (32, 61),
            "Galileo": (62, 97),
            "SBAS": (98, 136),
            "BeiDou": (137, 199),
            "QZSS": (200, 206),
        }

        # Codes for the satellite for each constelation
        sat_const_codes = {
            "G": "GPS",
            "R": "GLONASS",
            "E": "Galileo",
            "S": "SBAS",
            "C": "BeiDou",
            "J": "QZSS",
        }

        # Values for all satellites
        sat_vals = {
            "G": (1, 32),
            "R": (1, 30),
            "E": (1, 36),
            "S": (120, 158),
            "C": (1, 63),
            "J": (1, 7),
        }

        # Reverse map for name lookup
        cstl_to_index = {name: idx for idx, name in sat_const_ranges.items()}
        code_to_index = {name: idx for idx, name in sat_const_codes.items()}

        #  Initialize the bitfield
        bitfield = int.from_bytes(b"\x00" * 28, byteorder="big")

        if default_sats is True:
            # Enable GPS constelation
            bitfield |= 0xFFFFFFFF
            # Enable Galileo constelation
            bitfield |= ((1 << 36) - 1) << 62

        if constelation:
            for cstl in constelation:
                try:
                    cstl_range = sat_const_ranges.get(cstl)

                    if cstl_range is not None:
                        num_of_sats = cstl_range[1] - cstl_range[0] + 1
                        bitfield |= ((1 << num_of_sats) - 1) << cstl_range[0]
                    else:
                        typer.secho(
                            f"Error: Unknown constelation name '{cstl}'", fg="red"
                        )
                        typer.secho(
                            f"Valid names: {', '.join(sorted(sat_const_ranges.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)
                except ValueError:
                    typer.secho(
                        f"Error: Invalid constelation '{cstl}'. Use '-cstl NAME' or '--constelation NAME'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        if satellite:
            for sat in satellite:
                try:
                    sat_code = sat[0]
                    sat_num = int(sat[1:])
                    sat_const = sat_const_codes.get(sat_code)

                    if sat_const is not None:
                        cstl_range = sat_const_ranges.get(sat_const)

                        if (
                            not sat_vals[sat_code][0]
                            <= sat_num
                            <= sat_vals[sat_code][1]
                        ):
                            typer.secho(f"Error: Unknown value for '{sat}'", fg="red")
                            typer.secho(
                                f"Valid values: {sat_code}{sat_vals[sat_code][0]} - {sat_code}{sat_vals[sat_code][1]}"
                            )
                            raise typer.Exit(code=1)

                        # for SBAS
                        if sat_code == "S":
                            sat_num -= 119
                        bitfield |= 1 << (cstl_range[0] + sat_num - 1)
                        # bitfield |= ((1 << (sat_num - 1))) << cstl_range[0]
                    else:
                        typer.secho(f"Error: Unknown satellite name '{sat}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(sat_const_codes.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid satellite '{sat}'.  Use '-stl NAME' or '--satellite NAME'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        payload_bytes = bitfield.to_bytes(28, byteorder="big")

        # Show what we're sending
        typer.secho("\nSatellite Tracking Configuration:", fg="cyan", bold=True)
        enabled_sats = parse_bitfield(
            bitfield, sat_const_ranges, sat_vals, sat_const_codes
        )
        for const, sats in enabled_sats.items():
            if sats:
                typer.secho(f" [{const:12s}]: {sats}", fg="green")

        typer.secho(f"Bitfield:0x{bitfield:08X}")

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
def get_satellite_usage(
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
