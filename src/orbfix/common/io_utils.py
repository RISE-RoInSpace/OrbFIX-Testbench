from __future__ import annotations

import base64
import codecs
import os
import re
import sys
from typing import Optional

__all__ = [
    "hexdump",
    "PayloadSpecError",
    "parse_payload",
    "parse_one_byte_spec",
    "looks_like_hex",
]

def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)

def looks_like_hex(s: str) -> bool:
    s_clean = re.sub(r"[\s_]+", "", s).replace("0x", "").replace("0X", "")
    return bool(s_clean) and all(c in "0123456789abcdefABCDEF" for c in s_clean) and len(s_clean) % 2 == 0

class PayloadSpecError(ValueError):
    pass

def parse_payload(spec: Optional[str]) -> bytes:
    if spec is None or spec == "":
        return b""

    if spec.startswith("@"):
        path = spec[1:]
        if path == "-":
            return sys.stdin.buffer.read()
        if not os.path.exists(path):
            raise PayloadSpecError(f"File not found: {path}")
        with open(path, "rb") as f:
            return f.read()

    prefix, colon, rest = spec.partition(":")
    if colon:
        key = prefix.lower()
        if key == "hex":
            try:
                return bytes.fromhex(rest.replace("0x", "").replace("0X", ""))
            except ValueError as e:
                raise PayloadSpecError(f"Invalid hex payload: {e}")
        elif key in ("ascii", "str"):
            try:
                return codecs.decode(rest, "unicode_escape").encode("ascii")
            except Exception as e:
                raise PayloadSpecError(f"Invalid ASCII payload: {e}")
        elif key in ("utf8", "utf-8"):
            try:
                return codecs.decode(rest, "unicode_escape").encode("utf-8")
            except Exception as e:
                raise PayloadSpecError(f"Invalid UTF-8 payload: {e}")
        elif key in ("base64", "b64"):
            try:
                return base64.b64decode(rest, validate=True)
            except Exception as e:
                raise PayloadSpecError(f"Invalid base64 payload: {e}")
        else:
            raise PayloadSpecError("Unknown payload prefix. Use hex:, ascii:, utf8:, base64:, or @file.")

    if looks_like_hex(spec):
        return bytes.fromhex(spec.replace("0x", "").replace("0X", ""))
    try:
        return codecs.decode(spec, "unicode_escape").encode("utf-8")
    except Exception as e:
        raise PayloadSpecError(f"Could not parse payload: {e}")

def parse_one_byte_spec(spec: Optional[str], what: str = "system id") -> Optional[int]:
    if spec is None or spec == "":
        return None
    if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", spec):
        val = int(spec, 0)
        if not (0 <= val <= 0xFF):
            raise PayloadSpecError(f"{what} must be 0..255, got {val}")
        return val
    raw = parse_payload(spec)
    if len(raw) != 1:
        raise PayloadSpecError(f"{what} must resolve to exactly 1 byte, got {len(raw)} bytes")
    return raw[0]

def _is_hex_string(s: str) -> bool:
    """Return True if s is a valid even-length hex string (optionally with 0x)."""
    if s.startswith(("0x", "0X")):
        s = s[2:]
    # allow optional spaces between bytes: "0A 0B"
    s_clean = s.replace(" ", "")
    return len(s_clean) > 0 and all(c in "0123456789abcdefABCDEF" for c in s_clean) and (len(s_clean) % 2 == 0)

def parse_payload_spec(payload_str: str) -> bytes:
    """Parse payload spec:
       - if payload_str starts with '0x' or is an even-length hex string -> interpret as hex bytes
       - otherwise -> encode as utf-8 text
    """
    if not payload_str:
        return b""
    s = payload_str.strip()
    # If user passed "0x01" or "01" or "0A0B" or "0a 0b", handle as hex
    if s.startswith(("0x", "0X")) or _is_hex_string(s):
        if s.startswith(("0x", "0X")):
            s = s[2:]
        s = s.replace(" ", "")
        return bytes.fromhex(s)
    # Otherwise treat as UTF-8 text
    return s.encode("utf-8")

