from __future__ import annotations

import os
import sys
import time

from .runtime_support import autostart_log, cfg_float, http_get

_WIN_ERROR_ALREADY_EXISTS = 183
_MUTEX_NAME = "Local\\VictusVoiceAssistantBriefingLogon"


def exit_if_duplicate_logon_instance(cfg: dict) -> None:
    """Optional lock to avoid rare duplicate starts."""
    if os.environ.get("VICTUS_SKIP_MUTEX") == "1":
        return
    if not cfg.get("logon_singleton_mutex", False):
        return
    if sys.platform != "win32":
        return
    import ctypes

    kernel = ctypes.windll.kernel32
    kernel.SetLastError(0)
    handle = kernel.CreateMutexW(None, True, _MUTEX_NAME)
    if not handle:
        autostart_log("mutex CreateMutexW failed; continuing anyway")
        return
    err = kernel.GetLastError()
    if err == _WIN_ERROR_ALREADY_EXISTS:
        autostart_log("exit: duplicate instance (mutex already held)")
        sys.exit(0)


def internet_reachable() -> bool:
    probes = (
        ("https://connectivitycheck.gstatic.com/generate_204", lambda r: r.status_code == 204),
        ("http://www.msftconnecttest.com/connecttest.txt", lambda r: r.ok and "Microsoft" in (r.text or "")),
        (
            "https://api.open-meteo.com/v1/forecast?latitude=28.6&longitude=77.3&current=temperature_2m",
            lambda r: r.status_code == 200,
        ),
        ("https://www.google.com", lambda r: r.status_code < 500),
    )
    for url, ok in probes:
        try:
            response = http_get(url, timeout=4)
            if ok(response):
                return True
        except Exception:
            continue
    return False


def wait_for_internet(cfg: dict) -> None:
    max_wait = cfg_float(cfg, "internet_wait_max_seconds", 600, 0.0, 3600.0)
    poll = cfg_float(cfg, "internet_check_poll_seconds", 1.5, 0.5, 30.0)
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if internet_reachable():
            autostart_log("internet reachable")
            return
        time.sleep(poll)
    autostart_log(f"internet wait gave up after {max_wait}s (will try briefing anyway)")


def run_startup_gates(cfg: dict) -> None:
    if os.environ.get("VICTUS_NO_DELAY") == "1":
        return
    login_delay = cfg_float(cfg, "login_delay_seconds", 25, 0.0, 300.0)
    if login_delay > 0:
        autostart_log(f"login delay {login_delay}s")
        time.sleep(login_delay)
    exit_if_duplicate_logon_instance(cfg)
    wait_for_internet(cfg)
    pad = cfg_float(cfg, "post_internet_delay_seconds", 15, 0.0, 120.0)
    if pad > 0:
        autostart_log(f"post-internet delay {pad}s (lets Windows audio session start)")
        time.sleep(pad)
    autostart_log("internet check finished, building script")

