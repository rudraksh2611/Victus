from __future__ import annotations

import json
import os
import sys
import time
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
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{CONFIG_PATH.name} is not valid JSON ({e.msg} at line {e.lineno}). "
            "Re-run setup or fix the file."
        ) from e
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG_PATH.name} must contain a JSON object at the top level.")
    return data


def cfg_float(cfg: dict, key: str, default: float, low: float, high: float) -> float:
    raw = cfg.get(key, default)
    try:
        value = float(raw) if raw is not None else float(default)
    except (TypeError, ValueError):
        value = float(default)
    return max(low, min(value, high))


# ---------------------------------------------------------------------------
# HTTP with retry/backoff — transient network blips should not kill briefings
# ---------------------------------------------------------------------------

_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def http_get(
    url: str,
    *,
    timeout: float,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 0.6,
) -> requests.Response:
    """GET with bounded retries on connection errors / transient 5xx responses."""
    last_exc: BaseException | None = None
    attempts = max(1, int(retries))
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout, params=params)
            if response.status_code in _TRANSIENT_STATUSES and attempt < attempts:
                autostart_log(f"http_get transient {response.status_code} for {url} (attempt {attempt})")
                time.sleep(backoff * attempt)
                continue
            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            autostart_log(f"http_get attempt {attempt} for {url} failed: {e!r}")
            if attempt < attempts:
                time.sleep(backoff * attempt)
        except requests.RequestException as e:
            last_exc = e
            break
    assert last_exc is not None
    raise last_exc


def http_get_json(
    url: str,
    *,
    timeout: float,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 0.6,
) -> dict:
    response = http_get(url, timeout=timeout, params=params, retries=retries, backoff=backoff)
    response.raise_for_status()
    return response.json()
