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

app = typer.Typer(help="Get or set the tracking loop parameters.")

CMD_ID = 0x000A
DEFAULT_SYSID = "0x6A"


# Parser for responses to this command
@register(CMD_ID)
def _parse_tracking_loop_parameters(decoded):
    """
    Command 0x000A: Tracking loop parameters (Get/Set)
    Payload: 193 bytes
      - Byte offset   0: X4     - Bitfield of the supported satellite signals
      - Byte offset   4: U2[27] - Array of the DLLBandwidth values for each signal, Hz 8 100
      - Byte offset  58: U1[27] - Array of the PLLBandwidth values for each signal, Hz
      - Byte offset  85: U2[27] - Array of the MaxTpDLL values for each signal, Ms
      - Byte offset 139: U1[27] - Array of the MaxTpPLL values for each signal, ms
      - Byte offset 166: U1[27] - Array of the Adaptive value for each signal
    """
    pl: bytes = getattr(decoded, "payload", b"") or b""

    if len(pl) < 193:
        try:
            s = pl.rstrip(b"\x00").decode("utf-8")
            if s and all(31 < ord(ch) < 127 or ch in "\r\n\t ._:-/()" for ch in s):
                return (f"Received: {s}", {"received": s})
        except Exception:
            pass
    # Build from user-friendly options
    signal_map = {
        0: "GPSL1CA",
        1: "Reserved1",
        2: "Reserved2",
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

    # Read first 4 bytes as the signal bitfield (32 bits = signals 0-31)
    # Big-endian interpretation per protocol standard
    bitfield = int.from_bytes(pl[:4], byteorder="big")

    # Decode which satellite IDs are enabled (bit N set → satellite N tracked)
    enabled_sigs = [i for i in range(32) if (bitfield >> i) & 1]

    DLLBandwidth_bytes = pl[4:58]
    DLLBandwidth_arr = [
        int.from_bytes(DLLBandwidth_bytes[i : i + 2], byteorder="big")
        for i in range(0, 54, 2)
    ]

    PLLBandwidth_arr = list(pl[58:85])

    MaxTpDLL_bytes = pl[85:139]
    MaxTpDLL_arr = [
        int.from_bytes(MaxTpDLL_bytes[i : i + 2], byteorder="big")
        for i in range(0, 54, 2)
    ]

    MaxTpPLL_arr = list(pl[139:166])
    Adaptive_arr = list(pl[166:193])

    if enabled_sigs:
        sig_list = ", ".join(str(s) for s in enabled_sigs)
        result = f"Tracking loop parameters: {len(enabled_sigs)} signals enabled\n"
        result += f"  Signals IDs: {sig_list};\n"
        result += f"  [index] signal_type: DLLBandwidth Hz / 100 - PLLBandwidth Hz - MaxTpDLL ms - MaxTpPLL ms - Adaptive \n"

        for i in range(27):
            sig_name = signal_map.get(i, f"Signal_{i}")
            sig_DLL_val = DLLBandwidth_arr[i]
            sig_PLL_val = PLLBandwidth_arr[i]
            sig_MaxTpDLL_val = MaxTpDLL_arr[i]
            sig_MaxTpPLL_val = MaxTpPLL_arr[i]
            sig_Adaptive_val = Adaptive_arr[i]
            result += f"  [{i:5d}] {sig_name:11}: {sig_DLL_val:12d} Hz / 100 - {sig_PLL_val:12d} Hz - {sig_MaxTpDLL_val:8d} ms - {sig_MaxTpPLL_val:8d} ms - {sig_Adaptive_val:8d}\n"

        return (
            result,
            {
                "signals_count": len(enabled_sigs),
                "signals_ids": enabled_sigs,
                "bitfield_hex": f"0x{bitfield:08X}",
            },
        )
    else:
        return (
            f"Tracking loop parameters: No signals enabled (bitfield=0x{bitfield:08X})",
            {
                "signals_count": 0,
                "signals_ids": [],
                "bitfield_hex": f"0x{bitfield:08X}",
            },
        )


@app.command("set")
def set_tracking_loop_parameters(
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
    default: bool = typer.Option(
        None,
        "--default",
        "-d",
        help="Default values for all signals.",
        is_flag=True,
    ),
    default_dll: int = typer.Option(
        None,
        "--default_dll",
        "-dd",
        help="Default DLLBandwidth value for all signals. VALUE IS IN HZ*100",
    ),
    default_pll: int = typer.Option(
        None,
        "--default_pll",
        "-dp",
        help="Default PLLBandwidth value for all signals",
    ),
    default_maxdll: int = typer.Option(
        None,
        "--default_maxdll",
        "-dmd",
        help="Default MaxTpDLL value for all signals",
    ),
    default_maxpll: int = typer.Option(
        None,
        "--default_maxpll",
        "-dmp",
        help="Default MaxTpPLL value for all signals",
    ),
    default_adaptive: int = typer.Option(
        None,
        "--default_adaptive",
        "-da",
        help="Default Adaptive value for all signals",
    ),
    signal_dll: list[str] = typer.Option(
        None,
        "--signal_dll",
        "-sd",
        help="Set DLLBandwidth per signal: 'GPSL1CA=25' or '0=25'",
    ),
    signal_pll: list[str] = typer.Option(
        None,
        "--signal_pll",
        "-sp",
        help="Set PLLBandwidth per signal: 'GPSL1CA=15' or '0=15'",
    ),
    signal_maxdll: list[str] = typer.Option(
        None,
        "--signal_maxdll",
        "-smd",
        help="Set MaxTpDLL per signal: 'GPSL1CA=100' or '0=100'",
    ),
    signal_maxpll: list[str] = typer.Option(
        None,
        "--signal_maxpll",
        "-smp",
        help="Set MaxTpPLL per signal: 'GPSL1CA=10' or '0=10'",
    ),
    signal_adaptive: list[str] = typer.Option(
        None,
        "--signal_adaptive",
        "-sa",
        help="Set Adaptive per signal: 'GPSL1CA=1' or '0=1'",
    ),
    payload: str | None = typer.Option(
        None, "--payload", help="Raw hex payload (overrides other options)"
    ),
):
    """
    Set tracking loop paramaeters for GNSS signals.

    Examples:
        # Set all signals'parameters to the default values
        orbfix cmd tracking-loop-parameters set --default_dll 20 --default_pll 25
                --default_maxdll 12 --default_maxpll 12 --default_adaptive 0

        # Set specific parameters by signal name
        orbfix cmd tracking-loop-parameters -set -signal_dll GPSL1CA=25 --signal_pll GPSL1CA=15
            --signal_maxdll GPSL1CA=100 --signal_maxpll GPSL1CA=10 --signal_adaptive GPSL1CA=1

        # Can use indexing and mix approaches
        orbfix cmd tracking-loop-parameters set --default dll 68 --signal_dll GPSL1CA=0.25
            --signal_pll GPSL1CA=15 --signal_maxpll 12=24

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
        if len(payload_bytes) != 27:
            typer.secho(
                f"Warning: Payload is {len(payload_bytes)} bytes (expected 27 for CN0 mask)",
                fg="yellow",
            )
    else:
        # Build from user-friendly options
        signal_map = {
            0: "GPSL1CA",
            1: "Reserved1",
            2: "Reserved2",
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

        # Reverse map for name lookup
        name_to_index = {name: idx for idx, name in signal_map.items()}

        # Initialize bitfield
        bitfield = int.from_bytes(b"\x80\x00\x00\x00", byteorder="big")
        dll_values = [0] * 27
        pll_values = [0] * 27
        maxdll_values = [0] * 27
        maxpll_values = [0] * 27
        adaptive_values = [0] * 27

        # Default values
        if default is True:
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")
            dll_values = [25] * 27
            pll_values = [15] * 27
            maxdll_values = [100] * 27
            maxpll_values = [10] * 27
            adaptive_values = [1] * 27

        # Initialize default DLLBandwidth values to default or 25 Hz
        if default_dll is not None:
            if not 1 <= default_dll <= 500:
                typer.secho(
                    "Error: Default DLLBandwidth values must be 1 - 500 Hz / 100",
                    fg="red",
                )
                raise typer.Exit(code=1)
            dll_values = [default_dll] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize default PLLBandwidth values to default or 15 Hz
        if default_pll is not None:
            if not 1 <= default_pll <= 100:
                typer.secho(
                    "Error: Default PLLBandwidth values must be 1 - 100 Hz",
                    fg="red",
                )
                raise typer.Exit(code=1)
            pll_values = [default_pll] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize default MaxTpDLL values to default or 100 ms
        if default_maxdll is not None:
            if not 1 <= default_maxdll <= 500:
                typer.secho(
                    "Error: Default MaxTpDLL values must be 1 - 500 ms",
                    fg="red",
                )
                raise typer.Exit(code=1)
            maxdll_values = [default_maxdll] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize default MaxTpPLL values to default or 10
        if default_maxpll is not None:
            if not 1 <= default_maxpll <= 200:
                typer.secho(
                    "Error: Default MaxTpPLL values must be 1 - 200 ms",
                    fg="red",
                )
                raise typer.Exit(code=1)
            maxpll_values = [default_maxpll] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize default MaxTpPLL values to default or 10
        if default_maxpll is not None:
            if not 1 <= default_maxpll <= 200:
                typer.secho(
                    "Error: Default MaxTpPLL values must be 1 - 200 ms",
                    fg="red",
                )
                raise typer.Exit(code=1)
            maxpll_values = [default_maxpll] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Initialize default Adaptive values to default or 1
        if default_adaptive is not None:
            if not 0 <= default_adaptive <= 1:
                typer.secho(
                    "Error: Default Adaptive values must be 1(ON) or 0(OFF)",
                    fg="red",
                )
                raise typer.Exit(code=1)
            adaptive_values = [default_adaptive] * 27
            bitfield = int.from_bytes(b"\xff\xff\xff\xff", byteorder="big")

        # Apply per-signal overrides for DLLBandwidth
        if signal_dll:
            for spec in signal_dll:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    dll_val = int(val_str.strip())

                    if not 1 <= dll_val <= 500:
                        typer.secho(
                            f"Error: DLLBandwidth value for '{key}' must be 1-500 Hz / 100 (got {dll_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            dll_values[idx] = dll_val
                            bitfield |= 1 << idx
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        dll_values[idx] = dll_val
                        bitfield |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal DLLBandwidth value spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Apply per-signal overrides for PLLBandwidth
        if signal_pll:
            for spec in signal_pll:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    pll_val = int(val_str.strip())

                    if not 1 <= pll_val <= 100:
                        typer.secho(
                            f"Error: PLLBandwidth value for '{key}' must be 1-100 Hz (got {pll_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            pll_values[idx] = pll_val
                            bitfield |= 1 << idx
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        pll_values[idx] = pll_val
                        bitfield |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal PLLBandwidth value spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Apply per-signal overrides for MaxTpDLL
        if signal_maxdll:
            for spec in signal_maxdll:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    maxdll_val = int(val_str.strip())

                    if not 1 <= maxdll_val <= 500:
                        typer.secho(
                            f"Error: MaxTpDLL value for '{key}' must be 1-500 ms (got {maxdll_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            maxdll_values[idx] = maxdll_val
                            bitfield |= 1 << idx
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        maxdll_values[idx] = maxdll_val
                        bitfield |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal MaxTpDLL value spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Apply per-signal overrides for MaxTpPLL
        if signal_maxpll:
            for spec in signal_maxpll:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    maxpll_val = int(val_str.strip())

                    if not 1 <= maxpll_val <= 200:
                        typer.secho(
                            f"Error: MaxTpPLL value for '{key}' must be 1-200 ms (got {maxpll_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            maxpll_values[idx] = maxpll_val
                            bitfield |= 1 << idx
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        maxpll_values[idx] = maxpll_val
                        bitfield |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal MaxTpPLL value spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Apply per-signal overrides for Adaptive
        if signal_adaptive:
            for spec in signal_adaptive:
                try:
                    key, val_str = spec.split("=", 1)
                    key = key.strip()
                    adaptive_val = int(val_str.strip())

                    if not 0 <= adaptive_val <= 1:
                        typer.secho(
                            f"Error: Adaptive value for '{key}' must be 1(ON) or 0(OFF) (got {adaptive_val})",
                            fg="red",
                        )
                        raise typer.Exit(code=1)

                    # Try as index first
                    if key.isdigit():
                        idx = int(key)
                        if 0 <= idx <= 26:
                            adaptive_values[idx] = adaptive_val
                            bitfield |= 1 << idx
                        else:
                            typer.secho(
                                f"Error: Index {idx} out of range (0-26)", fg="red"
                            )
                            raise typer.Exit(code=1)
                    # Try as signal name
                    elif key.upper() in name_to_index:
                        idx = name_to_index[key.upper()]
                        adaptive_values[idx] = adaptive_val
                        bitfield |= 1 << idx
                    else:
                        typer.secho(f"Error: Unknown signal name '{key}'", fg="red")
                        typer.secho(
                            f"Valid names: {', '.join(sorted(name_to_index.keys()))}",
                            fg="yellow",
                        )
                        raise typer.Exit(code=1)

                except ValueError:
                    typer.secho(
                        f"Error: Invalid signal Adaptive value spec '{spec}'. Use 'NAME=VALUE' or 'INDEX=VALUE'",
                        fg="red",
                    )
                    raise typer.Exit(code=1)

        # Convert to bytes
        import struct

        payload_dll = b"".join(x.to_bytes(2, byteorder="big") for x in dll_values)
        payload_pll = b"".join(x.to_bytes(1, byteorder="big") for x in pll_values)
        payload_maxdll = b"".join(x.to_bytes(2, byteorder="big") for x in maxdll_values)
        payload_maxpll = b"".join(x.to_bytes(1, byteorder="big") for x in maxpll_values)
        payload_adaptive = b"".join(
            x.to_bytes(1, byteorder="big") for x in adaptive_values
        )

        payload_bytes = (
            bitfield.to_bytes(4, byteorder="big")
            + payload_dll
            + payload_pll
            + payload_maxdll
            + payload_maxpll
            + payload_adaptive
        )

        typer.secho(
            "Tracking loop parameters - signals configuration:", fg="cyan", bold=True
        )
        for idx in range(27):
            sig_name = signal_map.get(idx, f"Signal_{idx}")
            sig_track_val = (bitfield >> idx) & 1
            typer.secho(
                f"  [{idx:2d}] {sig_name:12s}: {sig_track_val:2d} \n",
                fg="green",
            )
        typer.echo()

        # Show DLL values
        typer.secho("DLLBandwidth values:", fg="cyan", bold=True)
        changed = [i for i in range(27) if dll_values[i] != (default_dll or 25)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {dll_values[idx]:2d} s",
                    fg="green",
                )
        if default_dll is not None:
            typer.secho(f"  All other signals: {default_dll} s", fg="white")
        typer.echo()

        # Show PLL values
        typer.secho("PLLBandwidth values:", fg="cyan", bold=True)
        changed = [i for i in range(27) if pll_values[i] != (default_pll or 15)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {pll_values[idx]:2d} s",
                    fg="green",
                )
        if default_pll is not None:
            typer.secho(f"  All other signals: {default_pll} s", fg="white")
        typer.echo()

        # Show MaxDLL values
        typer.secho("MaxTpDLL values:", fg="cyan", bold=True)
        changed = [i for i in range(27) if maxdll_values[i] != (default_maxdll or 100)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {maxdll_values[idx]:2d} s",
                    fg="green",
                )
        if default_maxdll is not None:
            typer.secho(f"  All other signals: {default_maxdll} s", fg="white")
        typer.echo()

        # Show MaxPLL values
        typer.secho("MaxTpPLL values:", fg="cyan", bold=True)
        changed = [i for i in range(27) if maxpll_values[i] != (default_maxpll or 10)]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {maxpll_values[idx]:2d} s",
                    fg="green",
                )
        if default_maxpll is not None:
            typer.secho(f"  All other signals: {default_maxpll} s", fg="white")
        typer.echo()

        # Show Adaptive values
        typer.secho("Adaptive values:", fg="cyan", bold=True)
        changed = [
            i for i in range(27) if adaptive_values[i] != (default_adaptive or 1)
        ]
        if changed:
            for idx in changed:
                sig_name = signal_map.get(idx, f"Signal_{idx}")
                typer.secho(
                    f"  [{idx:2d}] {sig_name:12s}: {adaptive_values[idx]:2d} s",
                    fg="green",
                )
        if default_adaptive is not None:
            typer.secho(f"  All other signals: {default_adaptive} s", fg="white")
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
def get_tracking_loop_parameters(
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
