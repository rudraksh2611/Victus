from __future__ import annotations

import os
import sys
import time

from .ui.overlay import OverlayController
from .runtime_support import autostart_log, cfg_float, http_get, is_autostart_logon

_WIN_ERROR_ALREADY_EXISTS = 183
_MUTEX_NAME = "Local\\VictusVoiceAssistantBriefingLogon"


class BriefingCancelled(Exception):
    """User pressed Stop on the overlay during countdown or early startup."""


def exit_if_duplicate_logon_instance(cfg: dict, overlay: OverlayController | None = None) -> None:
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
        if overlay:
            overlay.shutdown_quick()
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


def wait_for_internet(cfg: dict, overlay: OverlayController | None = None) -> None:
    max_wait = cfg_float(cfg, "internet_wait_max_seconds", 600, 0.0, 3600.0)
    poll = cfg_float(cfg, "internet_check_poll_seconds", 1.5, 0.5, 30.0)
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if overlay and overlay.poll_cancel():
            raise BriefingCancelled()
        if internet_reachable():
            autostart_log("internet reachable")
            return
        step = min(poll, max(0.0, deadline - time.monotonic()))
        if step <= 0:
            break
        t0 = time.monotonic()
        while time.monotonic() - t0 < step:
            if overlay and overlay.poll_cancel():
                raise BriefingCancelled()
            time.sleep(0.25)
    autostart_log(f"internet wait gave up after {max_wait}s (will try briefing anyway)")


def run_startup_gates(cfg: dict, overlay: OverlayController | None = None) -> None:
    try:
        _run_startup_gates_impl(cfg, overlay=overlay)
    except BriefingCancelled:
        raise
    except Exception as e:
        autostart_log(f"startup gate failed: {e!r}")
        raise


def _run_startup_gates_impl(cfg: dict, overlay: OverlayController | None = None) -> None:
    if os.environ.get("VICTUS_NO_DELAY") == "1":
        if overlay:
            overlay.preparing_audio()
        return
    login_delay = cfg_float(cfg, "login_delay_seconds", 25, 0.0, 300.0)
    if login_delay > 0:
        autostart_log(f"login delay {login_delay}s")
        remaining = int(login_delay)
        while remaining > 0:
            if overlay and overlay.poll_cancel():
                raise BriefingCancelled()
            if overlay:
                overlay.countdown_tick(remaining)
            time.sleep(1.0)
            remaining -= 1
    exit_if_duplicate_logon_instance(cfg, overlay=overlay)
    if overlay:
        overlay.waiting_network()
    wait_for_internet(cfg, overlay=overlay)
    pad = cfg_float(cfg, "post_internet_delay_seconds", 15, 0.0, 120.0)
    if is_autostart_logon():
        pad += cfg_float(cfg, "autostart_post_internet_extra_seconds", 8, 0.0, 120.0)
    if pad > 0:
        autostart_log(f"post-internet delay {pad}s (lets Windows audio session start)")
        if overlay:
            overlay.preparing_audio()
        t_end = time.monotonic() + pad
        while time.monotonic() < t_end:
            if overlay and overlay.poll_cancel():
                raise BriefingCancelled()
            time.sleep(0.25)
    autostart_log("internet check finished, building script")

