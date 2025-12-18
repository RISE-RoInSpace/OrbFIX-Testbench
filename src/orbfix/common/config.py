from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

# Config location: ~/.orbfix/config.toml  (override with ORBFIX_CONFIG_FILE if needed)
CONFIG_FILE = Path(os.environ.get("ORBFIX_CONFIG_FILE", Path.home() / ".orbfix" / "config.toml"))

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib

try:
    import tomli_w
except ModuleNotFoundError:
    tomli_w = None


def _ensure_parent() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as f:
            return tomllib.load(f)
    return {}


def save_config(cfg: Dict[str, Any]) -> None:
    _ensure_parent()
    if tomli_w:
        with CONFIG_FILE.open("wb") as f:
            tomli_w.dump(cfg, f)
        return
    lines = []
    serial = cfg.get("serial", {})
    if serial:
        lines.append("[serial]")
        port = serial.get("port")
        if port is not None:
            # Quote path; escape quotes
            port_escaped = str(port).replace('"', '\\"')
            lines.append(f'port = "{port_escaped}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_default_port() -> Optional[str]:
    cfg = load_config()
    return cfg.get("serial", {}).get("port")


def set_default_port(port: str) -> None:
    cfg = load_config()
    cfg.setdefault("serial", {})["port"] = port
    save_config(cfg)


def clear_default_port() -> None:
    cfg = load_config()
    if "serial" in cfg and "port" in cfg["serial"]:
        del cfg["serial"]["port"]
        if not cfg["serial"]:
            del cfg["serial"]
        save_config(cfg)
