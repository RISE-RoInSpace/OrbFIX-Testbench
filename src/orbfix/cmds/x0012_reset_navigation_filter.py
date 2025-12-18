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

app = typer.Typer(help="Reset navigation filter.")

CMD_ID = 0x0012
DEFAULT_SYSID = "0x6A"


@register(CMD_ID)
def _parse_reset_navigation_filter(decoded):
    """
    Command 0x0012: Reset navigation filter (Set)
    Payload:
      - Byte offset  0: X1     - Bitfield for the reset levels: PVT or AmbRTK.
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 1:
        try:
            s = ""
            return (f"Received: {s}", {"received": s})
        except Exception:
            pass

    bitfield = int.from_bytes(pl[0], byteorder="big")

    result = f"Reset navigation filter: (bitfield=0x{bitfield:08X})"
    result += f"  reset_pvt: {((bitfield >> 1) & 1):2d}"
    result += f"  reset_ambrtk: {((bitfield >> 0) & 1):2d}"

    return (
        result,
        {
            "bitfield_hex": f"0x{bitfield:08X}",
        },
    )


@app.command("set")
def set_reset_navigation_filter(
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
    reset_pvt: bool = typer.Option(
        None,
        "--reset_pvt",
        "-rp",
        help="Reset the whole PVT filter, including RTK ambiguities and INS/GNSS filter",
        is_flag=True,
    ),
    reset_ambrtk: bool = typer.Option(
        None,
        "--reset_ambrtk",
        "-ra",
        help="Reset only the ambiguities used in RTK positioning to float status",
        is_flag=True,
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Reset the navigation filter.

    Examples:
        # Reset the whole PVT filter
        orbfix cmd reset-navigation-filter set --reset_pvt

        # Reset the ambiguities used in RTK positioning
        orbfix cmd reset-navigation-filter set --reset_ambrtk
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
        if len(payload_bytes) != 1:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 1 for level bitfield)",
                fg="yellow",
            )
    else:
        # Initialize bitfield
        bitfield = int.from_bytes(b"\x00", byteorder="big")

        if reset_pvt is True:
            bitfield |= 1 << 1

        if reset_ambrtk is True:
            bitfield |= 1 << 0

        payload_bytes = bitfield.to_bytes(1, "big")

        typer.secho("Reset navigation filter:", fg="cyan", bold=True)
        typer.secho(
            f"  reset_pvt: {((bitfield >> 1) & 1):2d}",
            fg="green",
        )
        typer.secho(
            f"  reset_ambrtk: {((bitfield >> 0) & 1):2d}",
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
