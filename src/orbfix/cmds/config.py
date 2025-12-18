from __future__ import annotations

import typer
from ..common.config import set_default_port, get_default_port, clear_default_port, CONFIG_FILE

app = typer.Typer(help="Configure OrbFIX CLI defaults (saved in ~/.orbfix/config.toml).")

@app.command("set-port")
def set_port(
    port: str = typer.Argument(..., help="Serial port path, e.g. /dev/ttyUSB0 or COM5"),
):
    set_default_port(port)
    typer.secho(f"Saved default port: {port}\nConfig file: {CONFIG_FILE}", fg="green")

@app.command("show")
def show():
    port = get_default_port()
    if port:
        typer.echo(f"default port: {port}\nconfig file: {CONFIG_FILE}")
    else:
        typer.secho("No default port set.", fg="yellow")

@app.command("clear-port")
def clear():
    if get_default_port() is None:
        typer.secho("No default port to clear.", fg="yellow")
        raise typer.Exit(code=0)
    clear_default_port()
    typer.secho("Cleared default port.", fg="green")
