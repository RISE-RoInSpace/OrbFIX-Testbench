from __future__ import annotations
import math
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..transport.serial_rs422 import open_serial
import re, codecs

app = typer.Typer(help="Configure NMEA periodic timer.")

CMD_ID = 0x001B
DEFAULT_SYSID = "0x6A"
DEBUG_MODE = False

# Module-level endianness for the parser: ">" big-endian (network order), "<" little-endian.
PVT_ENDIAN = ">"

def _is_nan(x):
    return isinstance(x, float) and math.isnan(x)

def _fmt_num(v, fmt="{:.9f}", na="N/A"):
    if v is None:
        return na
    if isinstance(v, float) and _is_nan(v):
        return na
    try:
        return fmt.format(v)
    except Exception:
        return str(v)

def parse_cli_payload(s: str) -> bytes:
    s = s.strip()
    if s.lower().startswith("0x"):
        return bytes.fromhex(s[2:].replace("_","").replace(" ",""))  # hex -> bytes
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}\s*)+", s):
        return bytes.fromhex("".join(s.split()))                     # spaced hex -> bytes
    if "\\x" in s:
        return codecs.decode(s, "unicode_escape").encode("latin-1")  # \xNN -> bytes
    return s.encode("utf-8")

@register(CMD_ID)
def parse_get_NMEA_output(decoded, endian: str | None = None):
    pl: bytes = getattr(decoded, "payload", b"") or b""
    return (f"payload (hex): {pl}", {"payload_hex": pl})

@app.command("set")
def get_NMEA_output(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    payload: str | None = typer.Option(None, "--payload", help="Mosaic command/payload (string)"),
    endian: str = typer.Option("big", help="Byte order for PVT payload: 'big' or 'little'"),
):
    # Resolve endianness for parser
    global PVT_ENDIAN
    PVT_ENDIAN = ">" if endian.lower().startswith("b") else "<"

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

    if payload is not None:
        payload_bytes = parse_cli_payload(payload)
    else:
        payload_bytes=b"\x00\x00\x00\x00\x10"

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
        if DEBUG_MODE is True:
            # Reopen the serial port and monitor ASCII NMEA lines until Ctrl+C
            print("Monitoring NMEA (Ctrl+C to stop)...")
            try:
                with open_serial(resolved_port, baudrate=baud, timeout_s=1.0) as mon:
                    mon.reset_input_buffer()
                    while True:
                        line = mon.readline()
                        if not line:
                            continue
                        print(line.decode("ascii", errors="replace").rstrip())
            except KeyboardInterrupt:
                raise typer.Abort()
    except SerialException as e:
        typer.secho(f"Serial error: {e}", fg="red")
        raise typer.Exit(code=1)
