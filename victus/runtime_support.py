from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests


def _project_root() -> Path:
    """Project folder: repo root when running from source; folder containing the .exe when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
CONFIG_PATH = PROJECT_ROOT / "config.json"


def example_config_path() -> Path:
    """Bundled template (PyInstaller: inside _MEIPASS); dev: project root."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "config.example.json"
    return PROJECT_ROOT / "config.example.json"


def autostart_log(message: str) -> None:
    """Append one line for Task Scheduler/pythonw debugging."""
    try:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        log_dir = Path(base) / "VictusVoiceAssistant"
        log_dir.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
        with (log_dir / "briefing.log").open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def is_autostart_logon() -> bool:
    """True when launched via launch_at_logon.ps1 (scheduled task sets VICTUS_AUTOSTART=1)."""
    return os.environ.get("VICTUS_AUTOSTART", "").strip() == "1"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        hint = (
            "Copy config.example.json to config.json in the same folder as VictusMorningBriefing.exe."
            if getattr(sys, "frozen", False)
            else "Copy config.example.json to config.json in the project folder."
        )
        raise FileNotFoundError(f"Missing {CONFIG_PATH.name}. {hint}")
    # Accept UTF-8 with/without BOM (PowerShell may save JSON with BOM).
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def cfg_float(cfg: dict, key: str, default: float, low: float, high: float) -> float:
    value = float(cfg.get(key, default))
    return max(low, min(value, high))


def http_get(url: str, *, timeout: float, params: dict | None = None) -> requests.Response:
    return requests.get(url, timeout=timeout, params=params)


def http_get_json(url: str, *, timeout: float, params: dict | None = None) -> dict:
    response = http_get(url, timeout=timeout, params=params)
    response.raise_for_status()
    return response.json()
