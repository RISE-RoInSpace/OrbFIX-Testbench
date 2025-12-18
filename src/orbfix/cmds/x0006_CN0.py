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
from ..common.monitor_proxy import try_monitor_proxy
from ..common import RISECommand as RS
from .parsers import parse_decoded

app = typer.Typer(help="Get or set the C/N0 Mask")

CMD_ID = 0x0006
DEFAULT_SYSID = "0x6A"


# Parser for responses to this command
@register(CMD_ID)
def _parse_cn0_mask(decoded):
    """
    Command 0x0006: C/N0 Mask (Get/Set)
    Payload: 1 byte
      - Byte 1: U1 -  C/N0 threshold (Signal mask in 0-60 dB-Hz)
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""
    result = "C/N0 Mask Threshold:\n"

    if len(pl) <= 1:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s == "?":
                return (f"Received: {s}", {"received": s})
            else:
                mask = int.from_bytes(pl, byteorder="big")
                result += f"  Received: {mask} dB-Hz\n"
                print("aici")
        except Exception:
            pass

    result = result.rstrip("\n")

    return (
        result,
        {
            "mask_value": {int.from_bytes(pl)},
        },
    )


@app.command("set")
def set_CN0(
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
    treshold: int = typer.Option(
        None, "--treshold", "-t", help="Set threshold value: --treshold 5"
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Set C/N0 mask threshold for GNSS signals.

    Examples:
      # Set C/N0 Mask treshold to default value (10)
      orbfix cmd cn0-mask set

      # Set C/N0 Mask treshold to 23
      orbfix cmd cn0-mask set --treshold 23

      # Set C/N0 Mask treshold to 16
      orbfix cmd cn0-mask set -t 16

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
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 1 for CN0 mask)",
                fg="yellow",
            )
    else:
        # Initialize all thresholds to default or 0
        if treshold is not None:
            if not 0 <= treshold <= 60:
                typer.secho("Error: Threshold must be 0-60 dB-Hz", fg="red")
                raise typer.Exit(code=1)
        else:
            treshold = 10

        # Convert to bytes
        payload_bytes = treshold.to_bytes(1, byteorder="big")

        # Show what we're sending
        typer.secho("\nC/N0 Mask Treshold:", fg="cyan", bold=True)
        typer.secho(
            f"  Mask: {treshold} dB-Hz",
            fg="green",
        )

    resp = try_monitor_proxy(
        CMD_ID, sys_id_val, payload_bytes, wait, decode=(not no_decode)
    )
    if resp is not None:
        if resp.get("ok"):
            # Prefer local decoding: reconstruct frames from hex
            frames_hex = resp.get("frames_hex", [])
            if frames_hex and no_decode:
                # Raw frames
                for hx in frames_hex:
                    print(hx)
            elif frames_hex:
                for hx in frames_hex:
                    fr = bytes.fromhex(hx)
                    decoded, err = RS.riseprotocol_decode(fr)
                    if err == 0:
                        human, _m = parse_decoded(decoded)
                        print(human)
                    else:
                        print(f"[decode error] {err}")
            else:
                # Fallback to server human if no frames returned
                human = resp.get("human", "")
                if human:
                    print(human)
        else:
            print(resp.get("error", "monitor error"))
        return

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
def get_CN0(
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

    resp = try_monitor_proxy(CMD_ID, sys_id_val, payload, wait, decode=(not no_decode))
    if resp is not None:
        if resp.get("ok"):
            # Prefer local decoding: reconstruct frames from hex
            frames_hex = resp.get("frames_hex", [])
            if frames_hex and no_decode:
                # Raw frames
                for hx in frames_hex:
                    print(hx)
            elif frames_hex:
                for hx in frames_hex:
                    fr = bytes.fromhex(hx)
                    decoded, err = RS.riseprotocol_decode(fr)
                    if err == 0:
                        human, _m = parse_decoded(decoded)
                        print(human)
                    else:
                        print(f"[decode error] {err}")
            else:
                # Fallback to server human if no frames returned
                human = resp.get("human", "")
                if human:
                    print(human)
        else:
            print(resp.get("error", "monitor error"))
        return

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
