from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec, parse_payload_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register

app = typer.Typer(help="Get or set the the parameters of the Receiver Autonomous Integrity Monitoring (RAIM) algorithm.")

CMD_ID = 0x0010
DEFAULT_SYSID = "0x6A"

# Parser for responses to this command
@register(CMD_ID)
def _parse_raim_level(decoded):
    """
    Command 0x0010: RAIM Level(Get/Set)
    Payload: 4 bytes
      - Byte 0 (U1): Mode
      - Byte 1 (U1): Pfa
      - Byte 2 (U1): Pmd
      - Byte 3 (U1): Reliability
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""
    if len(pl) == 4:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass

        mode = pl[0]

        # Mode mapping
        mode_map = {
            0x00:"Off",
            0x01: "On",
        }

        mode_str = mode_map.get(mode, f"Unknown(0x{mode:02X})")

        # Parse the other 3 bytes (signed hex or decimal)
        try:
            # user provides them as "-12", "-3", "-1", etc.
            pfa = int(pl[1])   # decimal or hex ("0xF4") both work
            pmd = int(pl[2])
            reliability = int(pl[3])

            # must be within -12..-1
            for value in (pfa, pmd, reliability):
                if value > 12 or value < 1:
                    raise ValueError

        except ValueError:
            typer.secho(f"Error: values must be integers between 1 and 12: pfa = {pfa}, pmd = {pmd}, reliability = {reliability}", fg="red")
            raise typer.Exit(code=1)

        result = "RAIM Level:\n"
        result += f"  Mode: {str(mode_str)}\n"
        result += f"  Pfa: -{str(pfa)}\n"
        result += f"  Pmd: -{str(pmd)}\n"
        result += f"  Reliability: -{str(reliability)}"

        return (
            result,
            {
                "mode": mode_str,
                "pfa": pfa,
                "pmd": pmd,
                "reliability": reliability,
            }
        )

@app.command("set")
def set_raim_level(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
    # User-friendly options
    mode: str = typer.Option(None, "--mode", "-m", help="Mode: off, on"),
    pfa: str = typer.Option(None, "--pfa", "-f", help="Pfa: 01 ... 0C"),
    pmd: str = typer.Option(None, "--pmd", "-p", help="Pmd: 01 ... 0C"),
    reliability: str = typer.Option(None, "--reliability", "-r", help="Reliability: 01 ... 0C"),
    payload: str | None = typer.Option(None, "--payload", help="Raw hex payload (overrides other options)"),
):
    """
    Set RAIM Level configuration.

    Examples:
      # Set all parameters
      orbfix cmd raim-level set --mode waas --pfa 8 --pmd 5 --reliability 2

    # Raw payload
      orbfix cmd raim-level set --payload 080809
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
        payload_bytes = parse_payload_spec(payload)
        if len(payload_bytes) != 4:
            typer.secho(f"Warning: Payload is {len(payload_bytes)} bytes (expected 4)", fg="yellow")
    else:
        # All parameters required for SET
        if not all([mode, pfa, pmd, reliability]):
            typer.secho("Error: All parameters required: --satellite, --sis-mode, --nav-mode, --do229", fg="red")
            raise typer.Exit(code=1)

        # Satellite mapping
        mode_map = {
            "off": 0x00,
            "on": 0x01,
        }

        # Parse and validate
        mode_lower = mode.lower()
        if mode_lower not in mode_map:
            typer.secho(f"Error: Unknown mode '{mode}'", fg="red")
            typer.secho(f"Valid values: {', '.join(mode_map.keys())}", fg="yellow")
            raise typer.Exit(code=1)
        mode_byte = mode_map[mode_lower]

        try:
            # user provides them as "12", "3", "1", etc.
            pfa_byte = int(pfa)
            pmd_byte = int(pmd)
            reliability_byte = int(reliability)

            for value in (pfa_byte, pmd_byte, reliability_byte):
                if value > 12 or value < 1:
                    raise ValueError

        except ValueError:
            typer.secho("Error: values must be integers between 1 and 12", fg="red")
            raise typer.Exit(code=1)

        payload_bytes = bytes([mode_byte, pfa_byte, pmd_byte, reliability_byte])
        # Show configuration
        typer.secho("\nRAIM Level Configuration:", fg="cyan", bold=True)
        typer.secho(f"  Mode: {mode}", fg="green")
        typer.secho(f"  Pfa: {pfa}", fg="green")
        typer.secho(f"  Pmd: {pmd}", fg="green")
        typer.secho(f"  Reliability: {reliability}", fg="green")
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
def get_raim_level(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    """Get current RAIM Level configuration."""
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

    # Empty payload for GET
    payload_bytes = b""

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
