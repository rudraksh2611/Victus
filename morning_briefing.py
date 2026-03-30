"""
Victus morning briefing entrypoint.

This file intentionally stays small so Task Scheduler can keep using the same path:
`morning_briefing.py`.
"""
from __future__ import annotations

import sys
import time
import traceback

from victus.briefing import build_briefing_segments
from victus.runtime_support import autostart_log, load_config
from victus.speech import print_installed_voices, speak_segments
from victus.startup_gate import BriefingCancelled, run_startup_gates
from victus.ui import OverlayController


def _format_exc(e: BaseException) -> str:
    return "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()


def speak_with_logging(segments: list[str], cfg: dict, overlay: OverlayController | None = None) -> None:
    speak_segments(segments, cfg, overlay=overlay)
    autostart_log("finished OK")


def main() -> int:
    autostart_log("briefing started")
    overlay: OverlayController | None = None
    try:
        cfg = load_config()
    except Exception as e:
        autostart_log(f"config load failed: {e!r}")
        print(_format_exc(e), file=sys.stderr)
        return 1

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
    if "--list-voices" in sys.argv:
        try:
            print_installed_voices()
        except Exception as e:
            print(_format_exc(e), file=sys.stderr)
            sys.exit(1)
    else:
        sys.exit(main())
