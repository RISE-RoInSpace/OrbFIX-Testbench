from __future__ import annotations

import sys
import os
import subprocess
from typing import List, Optional

import typer

from .cmds import config as config_cmd


from .cmds import x0001_version as version_cmd
from .cmds import x0002_orbfix_gnss_power as orbfix_gnss_power
from .cmds import x0003_reset_orbfix_gnss as reset_orbfix_gnss
from .cmds import x0004_housekeeping as housekeeping_cmd
from .cmds import x0005_firmware_update as firmware_update
from .cmds import x0006_CN0 as CN0
from .cmds import x0007_satellite_tracking as satellite_tracking
from .cmds import x0008_signal_tracking as signal_tracking
from .cmds import x0009_smoothing_interval as smoothing_interval

from .cmds import x000A_tracking_loop_parameters as tracking_loop_parameters
from .cmds import x000B_notch_filtering as notch_filtering
from .cmds import x000C_antenna_offset as antenna_offset
from .cmds import x000D_elevation_mask as elev_mask
from .cmds import x000E_ionosphere_model as ionosphere_model
from .cmds import x000F_pvt_mode as pvt_mode_cmd

from .cmds import x0010_raim_level as raim_level
from .cmds import x0011_receiver_dynamics as receiver_dynamics
from .cmds import x0012_reset_navigation_filter as reset_navigation_filter
from .cmds import x0013_satellite_usage as satellite_usage
from .cmds import x0014_sbas_corrections as sbas_corrections
from .cmds import x0015_signal_usage as signal_usage
from .cmds import x0016_troposphere_model as troposphere_model
from .cmds import x0017_clock_sync_threshold as clock_sync_threshold
from .cmds import x0018_pps_parameters as pps_parameters
from .cmds import x0019_timing_system as timing_system
from .cmds import x0020_orbfix_cold_restart as orbfix_cold_restart
from .cmds import x0021_save_to_boot as save_to_boot

from .cmds import x001B_get_NMEA_output as get_NMEA_output

from . import monitor as monitor_app

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files  # type: ignore

app = typer.Typer(help="OrbFIX bench utilities and test runners")

# ------------------------------
# Existing sub-apps grouped under `cmd`
# ------------------------------
cmd_app = typer.Typer(help="Low-level command utilities (per ICD command)")
cmd_app.add_typer(pvt_mode_cmd.app, name="pvt-mode")
cmd_app.add_typer(version_cmd.app, name="version")
cmd_app.add_typer(housekeeping_cmd.app, name="housekeeping")
cmd_app.add_typer(config_cmd.app, name="config")
cmd_app.add_typer(orbfix_gnss_power.app, name="orbfix-gnss-power")
cmd_app.add_typer(reset_orbfix_gnss.app, name="reset-orbfix-gnss")
cmd_app.add_typer(get_NMEA_output.app, name="get-NMEA-output")
cmd_app.add_typer(antenna_offset.app, name="antenna-offset")
cmd_app.add_typer(CN0.app, name="cn0-mask")
cmd_app.add_typer(elev_mask.app, name="elev-mask")
cmd_app.add_typer(satellite_tracking.app, name="satellite-tracking")
cmd_app.add_typer(signal_tracking.app, name="signal-tracking")
cmd_app.add_typer(ionosphere_model.app, name="ionosphere-model")
cmd_app.add_typer(troposphere_model.app, name="troposphere-model")
cmd_app.add_typer(clock_sync_threshold.app, name="clock-sync-threshold")
cmd_app.add_typer(sbas_corrections.app, name="sbas-corrections")
cmd_app.add_typer(receiver_dynamics.app, name="receiver-dynamics")
cmd_app.add_typer(raim_level.app, name="raim-level")
cmd_app.add_typer(timing_system.app, name="timing-system")
cmd_app.add_typer(signal_usage.app, name="signal-usage")
cmd_app.add_typer(smoothing_interval.app, name="smoothing-interval")
cmd_app.add_typer(satellite_usage.app, name="satellite-usage")
cmd_app.add_typer(notch_filtering.app, name="notch-filtering")
cmd_app.add_typer(pps_parameters.app, name="pps-parameters")
cmd_app.add_typer(orbfix_cold_restart.app, name="orbfix-cold-restart")
cmd_app.add_typer(save_to_boot.app, name="save-to-boot")

cmd_app.add_typer(firmware_update.app, name="firmware-update")
cmd_app.add_typer(tracking_loop_parameters.app, name="tracking-loop-parameters")
cmd_app.add_typer(reset_navigation_filter.app, name="reset-navigation-filter")

app.add_typer(cmd_app, name="cmd")
app.add_typer(monitor_app.app, name="monitor")

# Create scripts sub-app BEFORE using it
scripts_app = typer.Typer(help="Run packaged bash scripts.")


def _script_path(name: str) -> str:
    """Resolve a script bundled under orbfix/scripts/<name>."""
    p = files("orbfix").joinpath("scripts").joinpath(name)
    return str(p)

# ------------------------------
# Helper function (not a command)
# ------------------------------
def _run_script_impl(
    script: str,
    args: List[str] | None = None,
    bash: str = "/bin/bash",
    env: List[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Execute a bash script. Returns exit code."""
    script_fs_path = _script_path(script)

    if not os.path.exists(script_fs_path):
        typer.secho(f"Script not found in package: {script}", fg="red")
        return 2

    # Build environment
    run_env = os.environ.copy()
    if env:
        for kv in env:
            if "=" not in kv:
                typer.secho(f"Invalid --env '{kv}', expected KEY=VALUE", fg="red")
                return 2
            k, v = kv.split("=", 1)
            run_env[k] = v

    cmd = [bash, script_fs_path, *(args or [])]
    typer.secho(f"$ {' '.join(cmd)}", fg="cyan")
    if dry_run:
        return 0

    try:
        proc = subprocess.Popen(
            cmd,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
        ret = proc.wait()
    except FileNotFoundError:
        typer.secho(f"Interpreter not found: {bash}", fg="red")
        return 127

    if ret != 0:
        typer.secho(f"Script exited with {ret}", fg="red")

    return ret


# ------------------------------
# Command that wraps the helper
# ------------------------------
@scripts_app.command("run")
def run_script(
    script: str = typer.Argument(
        ..., help="Filename under orbfix/scripts (e.g. hw-smoke.sh)"
    ),
    args: Optional[List[str]] = typer.Argument(
        None, help="Arguments passed to the script"
    ),
    bash: str = typer.Option(
        "/bin/bash", help="Path to bash (Git-Bash/WSL on Windows)"
    ),
    env: Optional[List[str]] = typer.Option(
        None, "--env", "-e", help="Environment KEY=VALUE (can repeat)"
    ),
    dry_run: bool = typer.Option(False, help="Print command then exit"),
):
    """Run a packaged bash script."""
    ret = _run_script_impl(script, args=args, bash=bash, env=env, dry_run=dry_run)
    if ret != 0:
        raise typer.Exit(code=ret)


@scripts_app.command("smoke")
def smoke(
    port: Optional[str] = typer.Option(None, "--port", help="Serial port to test"),
    bash: str = typer.Option("/bin/bash", help="Path to bash"),
):
    """Run hardware smoke test."""
    args: List[str] = []
    if port:
        args += ["--port", port]

    # Call the helper, not the command
    ret = _run_script_impl("hw-smoke.sh", args=args, bash=bash)
    if ret != 0:
        raise typer.Exit(code=ret)


@scripts_app.command("sbas-corrections-test")
def sbas_corrections_test(
    port: Optional[str] = typer.Option(None, "--port", help="Serial port to test"),
    bash: str = typer.Option("/bin/bash", help="Path to bash"),
):
    """Run SBAS corrections test suite."""
    args: List[str] = []
    if port:
        args += ["--port", port]

    # Call the helper, not the command
    ret = _run_script_impl("x0014_sbas_corrections_test.sh", args=args, bash=bash)
    if ret != 0:
        raise typer.Exit(code=ret)


app.add_typer(scripts_app, name="scripts")


def main():
    app()

if __name__ == "__main__":
    main()
