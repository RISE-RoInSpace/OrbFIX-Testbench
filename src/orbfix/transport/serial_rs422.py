from __future__ import annotations

import struct
import time
from typing import List, Optional
from enum import Enum, auto
from dataclasses import dataclass, field

import serial
import serial.tools.list_ports

# === Protocol constants ===
SYNC = b"RS"
HEADER_LEN = 9            # RS + CRC(2) + SYSTEM(1) + CMD(2) + LEN(2)
EOL = 0x0A                
LEN_OFFSET = 7            # Where the 2-byte payload length lives
LEN_BIG_ENDIAN = True     # True => ">H", False => "<H"
RISE_MSG_SIZE = 2048      # Maximum message size

HEADER_R = ord('R')
HEADER_S = ord('S')

DEFAULT_BAUD = 115200
DEFAULT_READ_TIMEOUT_S = 0.1

__all__ = [
    "find_usb_device",
    "find_device",
    "wait_for_device",
    "open_serial",
    "open_serial_by_vidpid",
    "flush_serial",
    "read_frames",
    "DEFAULT_BAUD",
    "DEFAULT_READ_TIMEOUT_S",
]

# === FSM Parser ===
class RiseState(Enum):
    """FSM states for incremental RISE protocol parsing."""
    ST_WAIT_SYNC1 = auto()
    ST_WAIT_SYNC2 = auto()
    ST_READ_CRC_0 = auto()
    ST_READ_CRC_1 = auto()
    ST_READ_SUBSYS = auto()
    ST_READ_CMD_ID_0 = auto()
    ST_READ_CMD_ID_1 = auto()
    ST_READ_LEN_0 = auto()
    ST_READ_LEN_1 = auto()
    ST_READ_PAYLOAD = auto()
    ST_READ_EOL = auto()

@dataclass
class RiseParser:
    """State container for incremental RISE protocol decoder."""
    state: RiseState = RiseState.ST_WAIT_SYNC1
    buffer: bytearray = field(default_factory=lambda: bytearray(RISE_MSG_SIZE))
    pos: int = 0
    expected_length: int = 0

    def reset(self):
        """Reset parser to initial state."""
        self.state = RiseState.ST_WAIT_SYNC1
        self.pos = 0
        self.expected_length = 0


def _fsm_decode_byte(parser: RiseParser, byte: int) -> int:
    """
    Incrementally decode a single byte using FSM.
    Returns frame length when complete frame is decoded, 0 otherwise.

    Args:
        parser: Parser state object
        byte: Single byte to process (0-255)

    Returns:
        Frame length if complete, 0 if incomplete or error
    """
    state = parser.state

    if state == RiseState.ST_WAIT_SYNC1:
        if byte == HEADER_R:
            parser.buffer[0] = byte
            parser.pos = 1
            parser.state = RiseState.ST_WAIT_SYNC2

    elif state == RiseState.ST_WAIT_SYNC2:
        if byte == HEADER_S:
            parser.buffer[parser.pos] = byte
            parser.pos += 1
            parser.state = RiseState.ST_READ_CRC_0
        else:
            parser.reset()

    elif state == RiseState.ST_READ_CRC_0:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_CRC_1

    elif state == RiseState.ST_READ_CRC_1:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_SUBSYS

    elif state == RiseState.ST_READ_SUBSYS:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_CMD_ID_0

    elif state == RiseState.ST_READ_CMD_ID_0:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_CMD_ID_1

    elif state == RiseState.ST_READ_CMD_ID_1:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_LEN_0

    elif state == RiseState.ST_READ_LEN_0:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.state = RiseState.ST_READ_LEN_1
        parser.expected_length = byte << 8  # Big-endian high byte

    elif state == RiseState.ST_READ_LEN_1:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        parser.expected_length |= byte  # Big-endian low byte

        # Validate total message size
        if HEADER_LEN + parser.expected_length > RISE_MSG_SIZE:
            parser.reset()
            return 0

        # Skip to EOL if payload length is 0
        parser.state = (RiseState.ST_READ_EOL if parser.expected_length == 0
                       else RiseState.ST_READ_PAYLOAD)

    elif state == RiseState.ST_READ_PAYLOAD:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        if parser.pos == HEADER_LEN + parser.expected_length:
            parser.state = RiseState.ST_READ_EOL

    elif state == RiseState.ST_READ_EOL:
        parser.buffer[parser.pos] = byte
        parser.pos += 1
        if byte != EOL:
            parser.reset()
            return 0
        # Complete frame received
        frame_len = parser.pos
        parser.reset()
        return frame_len

    return 0


# === Device discovery ===

def find_usb_device(target_vid: str, target_pid: str) -> Optional[str]:
    target_vid = target_vid.lower()
    target_pid = target_pid.lower()
    for port in serial.tools.list_ports.comports():
        if port.vid is None or port.pid is None:
            continue
        vid = f"{port.vid:04x}"
        pid = f"{port.pid:04x}"
        if vid == target_vid and pid == target_pid:
            return port.device
    return None


def find_device(vid: str, pid: str) -> Optional[str]:
    return find_usb_device(vid, pid)


def wait_for_device(vid: str, pid: str, timeout_s: float = 60.0, poll_s: float = 0.2) -> str:
    t0 = time.monotonic()
    while time.monotonic() - t0 <= timeout_s:
        path = find_device(vid, pid)
        if path:
            return path
        time.sleep(poll_s)
    raise TimeoutError(f"USB device {vid}:{pid} not found within {timeout_s}s")


# === Serial port management ===

def open_serial(port: str, baudrate: int = DEFAULT_BAUD, timeout_s: float = DEFAULT_READ_TIMEOUT_S) -> serial.Serial:
    ser = serial.Serial(
        port,
        baudrate=baudrate,
        timeout=timeout_s,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
        exclusive=True,
    )
    flush_serial(ser)
    return ser


def open_serial_by_vidpid(vid: str, pid: str, baudrate: int = DEFAULT_BAUD, timeout_s: float = DEFAULT_READ_TIMEOUT_S, wait_s: float | None = None) -> serial.Serial:
    """Open the first port that matches VID:PID. If wait_s is provided, block up to that long."""
    path = wait_for_device(vid, pid, timeout_s=wait_s) if wait_s else find_device(vid, pid)
    if not path:
        raise FileNotFoundError(f"No serial device for VID:PID {vid}:{pid}")
    return open_serial(path, baudrate=baudrate, timeout_s=timeout_s)


def flush_serial(ser: serial.Serial) -> None:
    """Flush input/output buffers safely."""
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except (serial.SerialException, OSError):
        pass


# === Frame reader (FSM-based) ===

def read_frames(
    ser: serial.Serial,
    deadline: float,
    *,
    require_eol: bool = True,  # Kept for API compatibility
    len_offset: int = LEN_OFFSET,  # Kept for API compatibility
    len_big_endian: bool = LEN_BIG_ENDIAN,  # Kept for API compatibility
    max_chunk: int = 256,
    debug_hex: bool = False,
) -> List[bytes]:
    """
    Read framed messages until deadline using FSM-based incremental parser.
    Returns all frames collected.

    Note: This function now uses FSM parsing internally. The require_eol,
    len_offset, and len_big_endian parameters are kept for backward
    compatibility but are not used (FSM enforces protocol structure).
    """
    parser = RiseParser()
    frames: List[bytes] = []

    while time.monotonic() < deadline:
        try:
            chunk = ser.read(max_chunk)
        except (serial.SerialException, OSError, ValueError):
            break

        if not chunk:
            # No data available; continue waiting until deadline
            continue

        if debug_hex:
            print(f"[RX] {chunk.hex(' ')}")

        # Process each byte through FSM
        for byte in chunk:
            frame_len = _fsm_decode_byte(parser, byte)
            if frame_len > 0:
                # Complete frame received
                frame = bytes(parser.buffer[:frame_len])
                frames.append(frame)
                if debug_hex:
                    print(f"[FRAME] {frame.hex(' ')}")

    # Return all frames collected
    return frames
