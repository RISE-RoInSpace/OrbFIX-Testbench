# src/orbfix/cmds/fw_direct.py
from __future__ import annotations
import sys
import threading
from pathlib import Path
import typer

from ..common.update import send_orbfix_zip
from ..common.io_utils import parse_one_byte_spec
from ..common.config import get_default_port
from ..transport.serial_rs422 import open_serial

DEFAULT_SYSID = "0x6A"
DEFAULT_BAUD = 115200

app = typer.Typer(help="Firmware update (direct)")

class StdoutWin:
    def addstr(self, s: str):
        sys.stdout.write(s)
    def refresh(self):
        sys.stdout.flush()
    def scroll(self, n: int):
        pass

@app.command("update")
def fw_update(
    zip_path: str = typer.Argument(..., help="Firmware .zip bundle"),
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid"),
    port: str | None = typer.Option(None, "--port", help="Explicit serial port path"),
    baud: int = typer.Option(DEFAULT_BAUD, "--baud"),
    data_size: int = typer.Option(1019, "--data-size", help="Per-packet data bytes (<=1021)"),
    wait: float = typer.Option(2.5, "--wait", help="Response timeout (s)"),
):
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0

    saved = get_default_port()
    resolved_port = port or (saved if saved and Path(saved).exists() else None)
    if not resolved_port:
        typer.secho("No valid port. Use --port or configure a saved port.", fg="red")
        raise typer.Exit(code=2)

    # Prepare simple output/log contexts
    output_win = StdoutWin()
    lock = threading.Lock()
    with open(
        "fw_update.log",
        "a",
        encoding="utf-8",
        buffering=1,
        newline="\n"
    ) as log_file:
        with open_serial(resolved_port, baudrate=baud, timeout_s=0.1) as ser:
            send_orbfix_zip(
                ser,
                output_win,
                lock,
                log_file,
                zip_path,
                sys_id_val=sys_id_val
            )

