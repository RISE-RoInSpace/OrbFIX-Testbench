from __future__ import annotations
from typing import Callable, Dict, Optional, Tuple, Any

ParseResult = Tuple[str, Optional[dict]]
_Registry: Dict[int, Callable[[Any], ParseResult]] = {}

def register(cmd_id: int) -> Callable[[Callable[[Any], ParseResult]], Callable[[Any], ParseResult]]:
    def _wrap(fn: Callable[[Any], ParseResult]) -> Callable[[Any], ParseResult]:
        _Registry[cmd_id] = fn
        return fn
    return _wrap

def parse_decoded(decoded: Any) -> ParseResult:
    cmd = getattr(decoded, "cmd_id", None)
    payload = getattr(decoded, "payload", b"") or b""
    handler = _Registry.get(cmd)
    if handler:
        try:
            return handler(decoded)
        except Exception as e:
            return (f"Parser for 0x{cmd:04X} raised: {e}. Payload hex: {payload.hex()}",
                    {"payload_hex": payload.hex()})
    return (f"No parser for 0x{(cmd if cmd is not None else 0):04X}. Payload hex: {payload.hex()}",
            {"payload_hex": payload.hex()})
