import struct
from pycrc.algorithms import Crc

# Constants
ENCODER_OFFSET = 9  # header size (without EOL)
RISECommand_SYNC_1 = 0x52  # 'R'
RISECommand_SYNC_2 = 0x53  # 'S'
ORBFIX_CTL_SUBSYSTEM_ID = 0x7A
# ORBFIX_GNSS can be any of 0x6A, 0x6B or 0x6C
ORBFIX_GNSS_SUBSYSTEM_IDS = (0x6A, 0x6B, 0x6C)
EOL = 0x0A  # '\n'


def compute_crc(command_info: bytes, arg: bytes) -> int:
    """CRC-16/CCITT-FALSE: width=16, poly=0x1021, init=0x0000, xor_out=0x0000, no reflection."""
    crc16 = Crc(width=16, poly=0x1021, reflect_in=False, xor_in=0x0000,
                reflect_out=False, xor_out=0x0000)
    return crc16.bit_by_bit(command_info + arg)


class RISECommand:
    """Parsed RISE command frame."""

    def __init__(self, buffer: bytes):
        # Minimal frame is 9-byte header + 1-byte EOL = 10
        if len(buffer) < 10:
            raise ValueError("Frame too short")

        # Header fields (big-endian)
        self.sync1 = buffer[0]
        self.sync2 = buffer[1]
        self.crc = struct.unpack(">H", buffer[2:4])[0]
        self.orbfix_id = buffer[4]
        self.cmd_id = struct.unpack(">H", buffer[5:7])[0]
        self.payload_length = struct.unpack(">H", buffer[7:9])[0]

        expected_len = ENCODER_OFFSET + self.payload_length + 1  # + EOL
        if len(buffer) != expected_len:
            raise ValueError("Length mismatch")

        self.payload = buffer[9:9 + self.payload_length] if self.payload_length else b""
        self.eol = buffer[-1]

    def validate_header(self) -> bool:
        return (self.sync1 == RISECommand_SYNC_1 and
                self.sync2 == RISECommand_SYNC_2 and
                self.eol == EOL)

    def validate_id(self) -> bool:
        """Accept either the main ORBFIX_CTL_SUBSYSTEM_ID or any ID in ORBFIX_GNSS_SUBSYSTEM_IDS."""
        return (self.orbfix_id == ORBFIX_CTL_SUBSYSTEM_ID or self.orbfix_id in ORBFIX_GNSS_SUBSYSTEM_IDS)

    def validate_crc(self) -> bool:
        crc_buff = struct.pack(">BHH", self.orbfix_id, self.cmd_id, self.payload_length)
        return self.crc == compute_crc(crc_buff, self.payload)


def riseprotocol_decode(command_buffer: bytes):
    """Decode a complete frame. Returns (RISECommand|None, err_code)."""
    try:
        entry = RISECommand(command_buffer)
        if not entry.validate_header():
            return None, -2
        if not entry.validate_id():
            return None, -3
        if not entry.validate_crc():
            return None, -4
        return entry, 0
    except Exception:
        return None, -1


def riseprotocol_encode(command_id: int, system: int, payload: bytes) -> bytes:
    """Build a complete frame"""
    crc_buff = struct.pack(">BHH", system, command_id, len(payload))
    crc = compute_crc(crc_buff, payload)

    encoded_message = bytearray(ENCODER_OFFSET + len(payload) + 1)
    encoded_message[:ENCODER_OFFSET] = struct.pack(
        ">BBHBHH",
        RISECommand_SYNC_1,
        RISECommand_SYNC_2,
        crc,
        system,
        command_id,
        len(payload),
    )
    if payload:
        encoded_message[9:9 + len(payload)] = payload
    encoded_message[-1] = EOL
    return bytes(encoded_message)