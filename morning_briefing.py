"""
Victus morning briefing entrypoint.

This file intentionally stays small so Task Scheduler can keep using the same path:
`morning_briefing.py`.
"""
from __future__ import annotations

import os
import sys

# Task Scheduler: use action "VictusMorningBriefing.exe", arguments "--autostart", "Start in" = install folder.
# (No .cmd wrapper required; matches what windows_autostart registers.)
if "--autostart" in sys.argv:
    os.environ["VICTUS_AUTOSTART"] = "1"

import time
import traceback

from victus.briefing import build_briefing_segments
from victus.runtime_support import CONFIG_PATH, autostart_log, cfg_float, is_autostart_logon, load_config
from victus.speech import print_installed_voices, speak_segments
from victus.windows_autostart import ensure_logon_task_if_configured
from victus.startup_gate import BriefingCancelled, run_startup_gates
from victus.ui import OverlayController


def _format_exc(e: BaseException) -> str:
    return "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()


def speak_with_logging(segments: list[str], cfg: dict, overlay: OverlayController | None = None) -> None:
    speak_segments(segments, cfg, overlay=overlay)
    autostart_log("finished OK")


def main() -> int:
    # One-shot: register logon task (for manual Task Scheduler troubleshooting or scripts).
    if (
        getattr(sys, "frozen", False)
        and sys.platform == "win32"
        and "--register-logon-task" in sys.argv
    ):
        from victus.windows_autostart import register_logon_task

        delay = 45
        try:
            cfg = load_config()
            delay = int(float(cfg.get("logon_task_delay_seconds", 45)))
        except Exception:
            pass
        ok, err = register_logon_task(delay_seconds=delay)
        if not ok:
            autostart_log(f"--register-logon-task failed: {err}")
        return 0 if ok else 1

    setup_only = "--setup" in sys.argv
    need_wizard = setup_only or (not CONFIG_PATH.exists())
    if need_wizard:
        try:
            from victus.ui.setup_wizard import run_setup_wizard

            saved = run_setup_wizard(editing=CONFIG_PATH.exists())
        except Exception as e:
            autostart_log(f"setup wizard failed: {e!r}")
            print(_format_exc(e), file=sys.stderr)
            return 1
        # --setup is a stand-alone "open settings" command: exit after the
        # wizard regardless of save/cancel so the user does not get a
        # surprise briefing immediately after editing their preferences.
        if setup_only:
            return 0 if saved else 1
        # First-run path (no config): require a save to continue into the
        # briefing — cancelling should not start a default-config run.
        if not saved:
            return 1

    autostart_log("briefing started")
    overlay: OverlayController | None = None
    try:
        cfg = load_config()
    except Exception as e:
        autostart_log(f"config load failed: {e!r}")
        print(_format_exc(e), file=sys.stderr)
        return 1

    # After install, first successful run registers the logon task so the EXE starts after each sign-in.
    ensure_logon_task_if_configured(cfg)

    bootstrap = cfg_float(cfg, "pre_overlay_delay_seconds", 0, 0, 600)
    if is_autostart_logon():
        bootstrap += cfg_float(cfg, "autostart_extra_delay_seconds", 18, 0, 600)
    if bootstrap > 0:
        autostart_log(f"session bootstrap delay {bootstrap}s (before overlay)")
        time.sleep(bootstrap)

    try:
        overlay = OverlayController(cfg)
        overlay.start()
        run_startup_gates(cfg, overlay=overlay)
        segments = build_briefing_segments(cfg)
        speak_with_logging(segments, cfg, overlay=overlay)
    except BriefingCancelled:
        autostart_log("briefing cancelled by user (Stop)")
        if overlay is not None:
            try:
                overlay.shutdown_quick()
            except Exception:
                pass
        return 0
    except Exception as e:
        msg = _format_exc(e)
        autostart_log(f"error: {msg}")
        print(msg, file=sys.stderr)
        if overlay is not None:
            try:
                overlay.show_error(msg)
                time.sleep(14)
            except Exception:
                pass
        if overlay is not None:
            try:
                overlay.shutdown_quick()
            except Exception:
                pass
        return 1
    return 0


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    if "--list-voices" in sys.argv:
        try:
            print_installed_voices()
        except Exception as e:
            print(_format_exc(e), file=sys.stderr)
            sys.exit(1)
    else:
        sys.exit(main())
