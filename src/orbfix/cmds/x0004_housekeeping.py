from __future__ import annotations
import typer
from ..common.io_utils import parse_one_byte_spec
from ..transport.serial_rs422 import find_usb_device, DEFAULT_BAUD, DEFAULT_READ_TIMEOUT_S
from .base import send_and_receive, DEFAULT_OVERALL_WAIT_S
from .parsers import register
from ..common.monitor_proxy import try_monitor_proxy
from ..common import RISECommand as RS
from .parsers import parse_decoded

app = typer.Typer(help="Request OrbFIX housekeeping info.")

CMD_ID = 0x0004
DEFAULT_SYSID = "0x6A"

@register(CMD_ID)
def _parse_housekeeping(decoded, endian=">"):
    """
    Parse Housekeeping payload:
      - System: 6×u32, 3×u64, 1×u32
      - Receiver (per provided struct):
          uint8  RFStatusFlags
          uint8  RFStatusNoRFBands
          uint8  ReceiverCPULoad
          uint8  ReceiverExtError
          uint8  ReceiverCmdCount
          uint8  ReceiverTemperatureC
          uint8  ReceiverPVTMode
          uint32 ReceiverUpTime
          uint32 ReceiverRxState
          uint32 ReceiverRxError
          uint8  RxQIOverallQuality
          uint8  RxQIGNSSSigMainAnt
          uint8  RxQIGNSSSigAuxAnt
          uint8  RxQIRFPwrMainAnt
          uint8  RxQIRFPwrAuxAnt
          uint8  RxQICPUHeadroom
    """
    import struct

    if endian not in (">", "<"):
        endian = ">"

    pl: bytes = getattr(decoded, "payload", b"") or b""
    n = len(pl)
    idx = 0

    def can_read(sz):
        return idx + sz <= n

    def read_u8():
        nonlocal idx
        if not can_read(1):
            return None, 0
        v = pl[idx]
        idx += 1
        return v, 1

    def read_u32():
        nonlocal idx
        if not can_read(4):
            return None, 0
        v = struct.unpack_from(f"{endian}I", pl, idx)[0]
        idx += 4
        return v, 4

    def read_u64():
        nonlocal idx
        if not can_read(8):
            return None, 0
        v = struct.unpack_from(f"{endian}Q", pl, idx)[0]
        idx += 8
        return v, 8

    def pretty_u8(v, sentinel=0xFF):
        return None if v is None or v == sentinel else v

    def pretty_u32(v, sentinel=0xFFFFFFFF):
        return None if v is None or v == sentinel else v

    def pretty_u64(v, sentinel=0xFFFFFFFFFFFFFFFF):
        return None if v is None or v == sentinel else v

    parsed_bytes = 0
    truncated = False

    # System parameters
    def get_u32():
        nonlocal parsed_bytes, truncated
        v, rb = read_u32(); parsed_bytes += rb
        if rb == 0: truncated = True
        return v

    def get_u64():
        nonlocal parsed_bytes, truncated
        v, rb = read_u64(); parsed_bytes += rb
        if rb == 0: truncated = True
        return v

    def get_u8():
        nonlocal parsed_bytes, truncated
        v, rb = read_u8(); parsed_bytes += rb
        if rb == 0: truncated = True
        return v

    temp_raw              = get_u32()
    cpuUsage              = get_u32()
    totalMem              = get_u32()
    freeMem               = get_u32()
    availableMem          = get_u32()
    sysUptime             = get_u32()

    totalDisk             = get_u64()
    freeDisk              = get_u64()
    usedDisk              = get_u64()

    processCount          = get_u32()

    RFStatusFlags         = get_u8()
    RFStatusNoRFBands     = get_u8()
    ReceiverCPULoad       = get_u8()
    ReceiverExtError      = get_u8()
    ReceiverCmdCount      = get_u8()
    ReceiverTemperatureC  = get_u8()
    ReceiverPVTMode       = get_u8()

    ReceiverUpTime        = get_u32()
    ReceiverRxState       = get_u32()
    ReceiverRxError       = get_u32()

    RxQIOverallQuality    = get_u8()
    RxQIGNSSSigMainAnt    = get_u8()
    RxQIGNSSSigAuxAnt     = get_u8()
    RxQIRFPwrMainAnt      = get_u8()
    RxQIRFPwrAuxAnt       = get_u8()
    RxQICPUHeadroom       = get_u8()

    # Post-process and units
    temp_pp = pretty_u32(temp_raw)
    temp_C = (temp_pp / 1000.0) if temp_pp is not None else None

    cpuUsage_pp = pretty_u32(cpuUsage)
    totalMem_pp = pretty_u32(totalMem)
    freeMem_pp = pretty_u32(freeMem)
    availableMem_pp = pretty_u32(availableMem)
    sysUptime_pp = pretty_u32(sysUptime)

    totalDisk_pp = pretty_u64(totalDisk)
    freeDisk_pp  = pretty_u64(freeDisk)
    usedDisk_pp  = pretty_u64(usedDisk)
    if usedDisk_pp is None and totalDisk_pp is not None and freeDisk_pp is not None:
        usedDisk_pp = max(totalDisk_pp - freeDisk_pp, 0)

    processCount_pp = pretty_u32(processCount)

    RFStatusFlags_pp        = pretty_u8(RFStatusFlags)
    RFStatusNoRFBands_pp    = pretty_u8(RFStatusNoRFBands)
    ReceiverCPULoad_pp      = pretty_u8(ReceiverCPULoad)
    ReceiverExtError_pp     = pretty_u8(ReceiverExtError)
    ReceiverCmdCount_pp     = pretty_u8(ReceiverCmdCount)
    ReceiverTemperatureC_pp = pretty_u8(ReceiverTemperatureC)
    ReceiverPVTMode_pp      = pretty_u8(ReceiverPVTMode)

    ReceiverUpTime_pp  = pretty_u32(ReceiverUpTime)
    ReceiverRxState_pp = pretty_u32(ReceiverRxState)
    ReceiverRxError_pp = pretty_u32(ReceiverRxError)

    RxQIOverallQuality_pp = pretty_u8(RxQIOverallQuality)
    RxQIGNSSSigMainAnt_pp = pretty_u8(RxQIGNSSSigMainAnt)
    RxQIGNSSSigAuxAnt_pp  = pretty_u8(RxQIGNSSSigAuxAnt)
    RxQIRFPwrMainAnt_pp   = pretty_u8(RxQIRFPwrMainAnt)
    RxQIRFPwrAuxAnt_pp    = pretty_u8(RxQIRFPwrAuxAnt)
    RxQICPUHeadroom_pp    = pretty_u8(RxQICPUHeadroom)

    def fmt_num(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "N/A"

    lines = []
    lines.append("Housekeeping:")
    lines.append("  System Parameters:")
    lines.append(f"    Temperature: {f'{temp_C:.3f} °C' if temp_C is not None else 'N/A'} (raw={temp_raw if temp_raw is not None else 'N/A'})")
    lines.append(f"    CPU Usage: {fmt_num(cpuUsage_pp, ' %')}")
    lines.append(f"    Total Memory: {fmt_num(totalMem_pp, ' MB')}")
    lines.append(f"    Free Memory: {fmt_num(freeMem_pp, ' MB')}")
    lines.append(f"    Available Memory: {fmt_num(availableMem_pp, ' MB')}")
    lines.append(f"    System Uptime: {fmt_num(sysUptime_pp, ' s')}")
    lines.append(f"    Total Disk: {fmt_num(totalDisk_pp, ' MB')}")
    lines.append(f"    Free Disk: {fmt_num(freeDisk_pp, ' MB')}")
    lines.append(f"    Used Disk: {fmt_num(usedDisk_pp, ' MB')}")
    lines.append(f"    Process Count: {fmt_num(processCount_pp)}")

    lines.append("  Receiver Parameters:")
    lines.append(f"    RF Status Flags: {('0x%02X' % RFStatusFlags_pp) if RFStatusFlags_pp is not None else 'N/A'}")
    lines.append(f"    RF Status No. RF Bands: {fmt_num(RFStatusNoRFBands_pp)}")
    lines.append(f"    Receiver CPU Load: {fmt_num(ReceiverCPULoad_pp, ' %')}")
    lines.append(f"    Receiver External Error: {('0x%02X' % ReceiverExtError_pp) if ReceiverExtError_pp is not None else 'N/A'}")
    lines.append(f"    Receiver Command Count: {fmt_num(ReceiverCmdCount_pp)}")
    lines.append(f"    Receiver Temperature: {fmt_num(ReceiverTemperatureC_pp, ' °C')}")
    lines.append(f"    Receiver PVT Mode: {fmt_num(ReceiverPVTMode_pp)}")
    lines.append(f"    Receiver Uptime: {fmt_num(ReceiverUpTime_pp, ' s')}")
    lines.append(f"    Receiver RX State: {fmt_num(ReceiverRxState_pp)}")
    lines.append(f"    Receiver RX Error: {fmt_num(ReceiverRxError_pp)}")

    lines.append("  Quality Indicators:")
    lines.append(f"    RxQI Overall Quality: {fmt_num(RxQIOverallQuality_pp)}")
    lines.append(f"    RxQI GNSS Sig Main Ant: {fmt_num(RxQIGNSSSigMainAnt_pp)}")
    lines.append(f"    RxQI GNSS Sig Aux Ant: {fmt_num(RxQIGNSSSigAuxAnt_pp)}")
    lines.append(f"    RxQI RF Pwr Main Ant: {fmt_num(RxQIRFPwrMainAnt_pp)}")
    lines.append(f"    RxQI RF Pwr Aux Ant: {fmt_num(RxQIRFPwrAuxAnt_pp)}")
    lines.append(f"    RxQI CPU Headroom: {fmt_num(RxQICPUHeadroom_pp)}")

    expected_len = (
        6*4 + 3*8 + 1*4   # system
        + 7*1 + 3*4 + 6*1 # receiver + QI
    )

    if truncated:
        lines.append(f"Note: payload truncated — parsed {parsed_bytes}/{n} bytes (expected {expected_len}).")

    pretty_text = "\n".join(lines)

    info = {
        "payload_len": n,
        "expected_len": expected_len,
        "parsed_bytes": parsed_bytes,
        "truncated": truncated,
        "payload_hex": pl.hex(),

        "temp_raw": temp_raw, "temp_C": temp_C,
        "cpuUsage": cpuUsage_pp, "totalMem": totalMem_pp, "freeMem": freeMem_pp,
        "availableMem": availableMem_pp, "sysUptime": sysUptime_pp,
        "totalDisk_MB": totalDisk_pp, "freeDisk_MB": freeDisk_pp, "usedDisk_MB": usedDisk_pp,
        "processCount": processCount_pp,

        "rf_flags_u8": RFStatusFlags_pp,
        "rf_no_bands_u8": RFStatusNoRFBands_pp,
        "receiver_cpu_load_u8": ReceiverCPULoad_pp,
        "receiver_ext_error_u8": ReceiverExtError_pp,
        "receiver_cmd_count_u8": ReceiverCmdCount_pp,
        "receiver_temp_C_u8": ReceiverTemperatureC_pp,
        "receiver_pvt_mode_u8": ReceiverPVTMode_pp,

        "receiver_uptime_s": ReceiverUpTime_pp,
        "receiver_rx_state": ReceiverRxState_pp,
        "receiver_rx_error": ReceiverRxError_pp,

        "rxqi_overall_u8": RxQIOverallQuality_pp,
        "rxqi_gnss_main_u8": RxQIGNSSSigMainAnt_pp,
        "rxqi_gnss_aux_u8": RxQIGNSSSigAuxAnt_pp,
        "rxqi_rf_main_u8": RxQIRFPwrMainAnt_pp,
        "rxqi_rf_aux_u8": RxQIRFPwrAuxAnt_pp,
        "rxqi_cpu_headroom_u8": RxQICPUHeadroom_pp,

        "endian": endian,
    }

    return (pretty_text, info)


@app.command("get")
def get_housekeeping(
    sysid: str = typer.Option(DEFAULT_SYSID, "--sysid", "--subsys", help="System/Subsys ID (1 byte)"),
    port: str | None = typer.Option(None, help="Explicit serial port path"),
    auto: bool = typer.Option(False, help="Auto-detect USB device by VID/PID"),
    baud: int = typer.Option(DEFAULT_BAUD, help="Baud rate"),
    timeout: float = typer.Option(DEFAULT_READ_TIMEOUT_S, help="Per-read timeout (s)"),
    wait: float = typer.Option(DEFAULT_OVERALL_WAIT_S, help="Overall receive window (s)"),
    no_decode: bool = typer.Option(False, help="Do not decode frames; just dump hex"),
):
    sys_id_val = parse_one_byte_spec(sysid, what="system id") or 0
    from ..common.config import get_default_port
    from ..transport.serial_rs422 import find_usb_device
    from pathlib import Path
    saved = get_default_port()
    resolved_port = (
        port
        or (saved if saved and Path(saved).exists() else None)
        or (find_usb_device(vid, pid) if auto else None)
    )
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
