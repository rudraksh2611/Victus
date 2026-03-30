"""
Victus morning briefing entrypoint.

This file intentionally stays small so Task Scheduler can keep using the same path:
`morning_briefing.py`.
"""
from __future__ import annotations

import sys

from victus.briefing_content import build_briefing_segments
from victus.runtime_support import autostart_log, load_config
from victus.speech_engines import print_installed_voices, speak_segments
from victus.startup_gate import run_startup_gates


def build_segments_with_fallback(cfg: dict) -> list[str]:
    try:
        return build_briefing_segments(cfg)
    except Exception as e:
        msg = f"Morning briefing failed: {e}. Check your internet connection and config.json."
        autostart_log(f"build failed: {e}")
        print(msg, file=sys.stderr)
        return [msg]


def speak_with_logging(segments: list[str], cfg: dict) -> None:
    try:
        speak_segments(segments, cfg)
        autostart_log("finished OK")
    except Exception as e:
        autostart_log(f"speak failed: {e!r}")
        raise


def main() -> None:
    autostart_log("briefing started")
    try:
        cfg = load_config()
    except Exception as e:
        autostart_log(f"config load failed: {e}")
        raise
    run_startup_gates(cfg)
    segments = build_segments_with_fallback(cfg)
    speak_with_logging(segments, cfg)


if __name__ == "__main__":
    if "--list-voices" in sys.argv:
        print_installed_voices()
    else:
        try:
            main()
        except Exception as e:
            autostart_log(f"uncaught: {e!r}")
            sys.exit(1)
