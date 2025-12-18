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

app = typer.Typer(help="Get/Set which signal types are used by the receiver.")

CMD_ID = 0x0015
DEFAULT_SYSID = "0x6A"


@register(CMD_ID)
def _parse_signal_usage(decoded):
    """
    Command 0x0015: Signal usage (Get/Set)
    Payload:
      - Byte offset  0: X4 - Bitfield of the supported PVT signals.
      - Byte offset  4: X4 - Bitfield of the supported Navigation data signals.
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 8:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    bitfield_pvt = int.from_bytes(pl[:4], byteorder="big")
    bitfield_navData = int.from_bytes(pl[4:], byteorder="big")

    # Signal type names per bit position
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

    # Decode which signals are enabled for PVT
    enabled_sigs_pvt = [i for i in range(32) if (bitfield_pvt >> i) & 1]

    # Decode which signals are enabled for navData
    enabled_sigs_navData = [i for i in range(32) if (bitfield_navData >> i) & 1]

    result = f"Satellite usage: (bitfield_pvt=0x{bitfield_pvt:08X}, bitfield_navData=0x{bitfield_navData:08X})\n"
    result += f"      PVT signal IDs:\n"

    for sig in enabled_sigs_pvt:
        sig_name = signal_map.get(sig, f"Signal_{sig}")
        result += f" [{sig:2d}] {sig_name:12s} \n"
    result = result.rstrip("\n")

    result += f"\n  navData signal IDs:\n"
    for sig in enabled_sigs_navData:
        sig_name = signal_map.get(sig, f"Signal_{sig}")
        result += f" [{sig:2d}] {sig_name:12s} \n"
    result = result.rstrip("\n")

    return (
        result,
        {
            "bitfield_pvt_hex": f"0x{bitfield_pvt:08X}",
            "bitfield_navData_hex": f"0x{bitfield_navData:08X}",
        },
    )


def parse_bitfield(bitfield, sat_const_ranges):
    enabled_sats = {}

    for const, (start, end) in sat_const_ranges.items():
        sats = []
        for i in range(start, end + 1):
            if (bitfield >> i) & 1:
                enabled_sat_num = i - start + 1
                sats.append(enabled_sat_num)
        enabled_sats[const] = sats

    return enabled_sats


@app.command("set")
def set_signal_usage(
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
    default_pvt: bool = typer.Option(
        None,
        "--default_pvt",
        "-dp",
        help="Enable the default signals for pvt",
        is_flag=True,
    ),
    default_navdata: bool = typer.Option(
        None,
        "--default_navdata",
        "-dn",
        help="Enable the default signals for navData",
        is_flag=True,
    ),
    signal_pvt: list[str] = typer.Option(
        None,
        "--signal_pvt",
        "-sp",
        help="Select a certain signal and enable PVT for it",
    ),
    signal_navdata: list[str] = typer.Option(
        None,
        "--signal_navdata",
        "-sn",
        help="Select a certain signal and enable navData for it",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Satellite Usage.

    Examples:
        # Enable default signals
        orbfix cmd signal-usage set --default_pvt --default_navdata
        orbfix cmd signal-usage set -dp -dn

        # Enable a certain signal for pvt
        orbfix cmd signal-usage set --signal_pvt GPSL1CA
        orbfix cmd signal-usage set --sp GLOL3

        # Enable a certain signal navdata
        orbfix cmd signal-usage set --signal_navdata GEOL1
        orbfix cmd signal-usage set -sn GEOL5

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
        if len(payload_bytes) != 8:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 8 for satellite bitfields)",
                fg="yellow",
            )
    else:
        # Signal type names per bit position
        signal_map = {
            0: "GPSL1CA",
            1: "GPSL1PY",
            2: "GPSL2PY",
            3: "GPSL2C",  #
            4: "GPSL5",
            5: "GLOL1CA",
            6: "GLOL2P",
            7: "GLOL2CA",  ## b1
            8: "GLOL3",
            9: "GALL1BC",
            10: "GALE6BC",
            11: "GALE5a",  #
            12: "GALE5b",
            13: "GALE5",
            14: "GEOL1",
            15: "GEOL5",  ## b2
            16: "BDSB1I",
            17: "BDSB2I",
            18: "BDSB3I",
            19: "BDSB1C",  #
            20: "BDSB2a",
            21: "BDSB2b",
            22: "QZSL1CA",
            23: "QZSL2C",  ## b3
            24: "QZSL5",
            25: "QZSL1CB",
            26: "NAVICL5",
        }

        # Reverse map for name lookup
        name_to_index = {name: idx for idx, name in signal_map.items()}

        #  Initialize the bitfield
        bitfield_pvt = int.from_bytes(
            b"\x00\x00\x00\x00\x00\x00\x00\x00", byteorder="big"
        )
        bitfield_navdata = int.from_bytes(
            b"\x00\x00\x00\x00\x00\x00\x00\x00", byteorder="big"
        )

        if default_pvt is True:
            # Enable default signals for pvt
            bitfield_pvt |= 0x3E1F
        if default_navdata is True:
            # Enable default signals for pvt
            bitfield_navdata |= 0x3E1F

        if signal_pvt:
            for sig in signal_pvt:
                try:
                    if sig.isdigit():
                        idx = int(sig)
                        if 0 <= sig <= 26:
                            bitfield_pvt |= 1 << sig
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    elif sig.upper() in name_to_index:
                        idx = name_to_index[sig.upper()]
                        bitfield_pvt |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{sig}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)
                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal '{sig}'. Use '--signal_pvt NAME' or '-sp NAME'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)
        if signal_navdata:
            for sig in signal_navdata:
                try:
                    if sig.isdigit():
                        idx = int(sig)
                        if 0 <= sig <= 26:
                            bitfield_navdata |= 1 << sig
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    elif sig.upper() in name_to_index:
                        idx = name_to_index[sig.upper()]
                        bitfield_navdata |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{sig}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)
                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal '{sig}'. Use '--signal_navdata NAME' or '-sn NAME'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        payload_bytes = bitfield_pvt.to_bytes(
            4, byteorder="big"
        ) + bitfield_navdata.to_bytes(4, byteorder="big")

        # Show what we're sending
        typer.secho("Signal Usage Configuration:", fg="cyan", bold=True)
        enabled_sigs_pvt = [i for i in range(32) if (bitfield_pvt >> i) & 1]
        enabled_sigs_navdata = [i for i in range(32) if (bitfield_navdata >> i) & 1]

        typer.secho("PVT signals:", fg="cyan", bold=True)
        for sig in enabled_sigs_pvt:
            sig_name_pvt = signal_map.get(sig, f"Signal_{sig}")
            typer.secho(f" [{sig:2d}]: {sig_name_pvt}", fg="green")

        typer.secho("NavData signals:", fg="cyan", bold=True)
        for sig in enabled_sigs_navdata:
            sig_name_navdata = signal_map.get(sig, f"Signal_{sig}")
            typer.secho(f" [{sig:2d}]: {sig_name_navdata}", fg="green")

        typer.secho(f"Bitfield_PVT:0x{bitfield_pvt:08X}")
        typer.secho(f"Bitfield_navData:0x{bitfield_navdata:08X}")

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
def get_signal_usage(
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
