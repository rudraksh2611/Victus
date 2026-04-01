from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import threading
import time

import pyttsx3

from ..briefing.content import soften_for_speech
from ..runtime_support import autostart_log, cfg_float
from ..ui.overlay import OverlayController


class SpeakingStopped(Exception):
    """User pressed × on the overlay during TTS; stop playback and exit speak_segments cleanly."""


def _seconds_per_word_from_edge_rate(rate_str: str) -> float:
    """Rough mapping from Edge rate string (e.g. +18%) to seconds per word for UI sync."""
    base = 0.44
    try:
        s = str(rate_str).strip().replace("%", "")
        if s.startswith("+"):
            mult = 1.0 + float(s[1:]) / 100.0
        elif s.startswith("-"):
            mult = 1.0 - float(s[1:]) / 100.0
        else:
            mult = float(s) if s else 1.0
    except ValueError:
        mult = 1.0
    mult = max(0.35, min(mult, 2.5))
    return base / mult


def _words_for_sync(text: str) -> list[str]:
    """Split into words for highlighting (keeps apostrophes inside words)."""
    t = soften_for_speech(text.strip())
    if not t:
        return []
    parts = re.findall(r"\S+", t)
    return parts if parts else [t]


def init_pygame_mixer_with_retries() -> None:
    import pygame

    try:
        pygame.init()
    except Exception as e:
        autostart_log(f"pygame.init warning: {e}")
    last_err: Exception | None = None
    for attempt in range(1, 5):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except Exception:
            pass
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            autostart_log(f"pygame mixer ready (attempt {attempt})")
            return
        except Exception as e:
            last_err = e
            autostart_log(f"pygame mixer attempt {attempt} failed: {e}")
            time.sleep(4)
    if last_err:
        raise last_err


async def speak_edge_chunked(
    segments: list[str],
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    pause_s: float,
    overlay: OverlayController | None = None,
) -> None:
    import edge_tts
    import pygame

    pause_s = min(max(0.0, pause_s), 1.0)
    lines = [t for t in (soften_for_speech(s.strip()) for s in segments if s.strip()) if t]
    if not lines:
        return

    init_pygame_mixer_with_retries()
    spw = _seconds_per_word_from_edge_rate(rate)

    async def synth(text: str) -> str:
        last_err: Exception | None = None
        for attempt in range(1, 6):
            fd, path = tempfile.mkstemp(suffix=".mp3", prefix="victus_")
            os.close(fd)
            try:
                comm = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume, pitch=pitch)
                await comm.save(path)
                return path
            except Exception as e:
                last_err = e
                autostart_log(f"edge synth attempt {attempt} failed: {e!r}")
                try:
                    os.remove(path)
                except OSError:
                    pass
                await asyncio.sleep(min(2.0 * attempt, 10.0))
        assert last_err is not None
        raise last_err

    async def playback_loop(line: str, current_path: str) -> None:
        words = _words_for_sync(line)
        est_ms = max(800, int(len(words) * spw * 1000))
        pygame.mixer.music.load(current_path)
        pygame.mixer.music.play()
        t0 = time.monotonic()
        max_pos = 0

        if overlay and words:
            overlay.speaking_chunk_words(words)

        while pygame.mixer.music.get_busy():
            if overlay and overlay.poll_stop_speaking():
                pygame.mixer.music.stop()
                raise SpeakingStopped()
            raw = pygame.mixer.music.get_pos()
            if raw < 0:
                pos_ms = int((time.monotonic() - t0) * 1000)
            else:
                pos_ms = raw
                max_pos = max(max_pos, pos_ms)
            denom = max(float(est_ms), float(max_pos), float(pos_ms), 1.0)
            prog = min(1.0, pos_ms / denom)
            frac = prog * max(len(words), 1)
            widx = min(len(words) - 1, max(0, int(frac))) if words else 0
            wfrac = frac - int(frac) if words else 0.0
            if overlay:
                overlay.speaking_tick(widx, prog, wfrac)
            await asyncio.sleep(0.05)

        if overlay and words:
            overlay.speaking_tick(len(words) - 1, 1.0, 0.0)

    current_path = await synth(lines[0])
    for i in range(len(lines)):
        line = lines[i]
        next_task: asyncio.Task[str] | None = None
        if i + 1 < len(lines):
            next_task = asyncio.create_task(synth(lines[i + 1]))

        try:
            await playback_loop(line, current_path)
        except SpeakingStopped:
            try:
                os.remove(current_path)
            except OSError:
                pass
            if next_task is not None:
                next_task.cancel()
                try:
                    await next_task
                except (asyncio.CancelledError, Exception):
                    pass
            raise

        if pause_s > 0:
            t0 = time.monotonic()
            while time.monotonic() - t0 < pause_s:
                if overlay and overlay.poll_stop_speaking():
                    try:
                        os.remove(current_path)
                    except OSError:
                        pass
                    if next_task is not None:
                        next_task.cancel()
                        try:
                            await next_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    raise SpeakingStopped()
                await asyncio.sleep(0.08)

        try:
            os.remove(current_path)
        except OSError:
            pass

        if next_task is not None:
            current_path = await next_task


async def speak_segments_edge(segments: list[str], cfg: dict, overlay: OverlayController | None = None) -> None:
    voice = (cfg.get("tts_voice") or "en-IN-NeerjaNeural").strip()
    rate = str(cfg.get("edge_speaking_rate", "+18%"))
    volume = str(cfg.get("edge_volume", "+0%"))
    pitch = str(cfg.get("edge_pitch", "+0Hz"))
    pause_s = cfg_float(cfg, "pause_between_sections_seconds", 0, 0.0, 1.0)
    mode = str(cfg.get("edge_playback_mode", "continuous")).lower().strip()

    nonempty = [s for s in segments if s.strip()]
    if not nonempty:
        return
    if mode == "chunked":
        await speak_edge_chunked(nonempty, voice, rate, volume, pitch, pause_s, overlay=overlay)
        return

    line = " ".join(soften_for_speech(s) for s in nonempty if s.strip())
    if line:
        await speak_edge_chunked([line], voice, rate, volume, pitch, 0, overlay=overlay)


def apply_sapi_voice(engine: pyttsx3.Engine, voice_hint: str | None) -> None:
    if not (voice_hint and str(voice_hint).strip()):
        return
    hint = str(voice_hint).strip().lower()
    voices = engine.getProperty("voices") or []
    for v in voices:
        name = (v.name or "").lower()
        vid = (getattr(v, "id", None) or "").lower()
        if hint in name or hint in vid:
            engine.setProperty("voice", v.id)
            return


def sapi_voice_hint(cfg: dict) -> str | None:
    explicit = (cfg.get("sapi_voice_hint") or "").strip()
    if explicit:
        return explicit
    edge_v = cfg.get("tts_voice") or ""
    if "Neural" in edge_v or (isinstance(edge_v, str) and edge_v.count("-") >= 2 and len(edge_v) > 12):
        return "Zira"
    return (edge_v or "").strip() or None


def speak_segments_sapi(segments: list[str], cfg: dict, overlay: OverlayController | None = None) -> None:
    rate = int(cfg.get("tts_rate", 200))
    pause_s = cfg_float(cfg, "pause_between_sections_seconds", 0, 0.0, 1.0)
    vol = cfg.get("tts_volume")
    voice_hint = sapi_voice_hint(cfg)
    spw = 60.0 / max(80, min(rate, 400)) * 0.5

    engine = pyttsx3.init()
    try:
        engine.setProperty("rate", rate)
        if vol is not None:
            engine.setProperty("volume", min(1.0, max(0.0, float(vol))))
        else:
            v = engine.getProperty("volume")
            engine.setProperty("volume", min(1.0, max(0.5, v)))
        apply_sapi_voice(engine, voice_hint)
    except Exception:
        pass

    for i, text in enumerate(segments):
        if not text.strip():
            continue
        if overlay and overlay.poll_stop_speaking():
            raise SpeakingStopped()
        line = text.strip()
        words = _words_for_sync(line)
        est = max(1.0, len(words) * spw)
        stop = threading.Event()
        user_stop = threading.Event()
        eng_ref: list = [engine]

        def pump_sapi(ov: OverlayController | None) -> None:
            t0 = time.monotonic()
            while not stop.is_set():
                if ov and ov.poll_stop_speaking():
                    user_stop.set()
                    stop.set()
                    try:
                        eng_ref[0].stop()
                    except Exception:
                        pass
                    return
                elapsed = time.monotonic() - t0
                prog = min(1.0, elapsed / est)
                if words and ov:
                    frac = prog * len(words)
                    widx = min(len(words) - 1, max(0, int(frac)))
                    wfrac = frac - int(frac)
                    ov.speaking_tick(widx, prog, wfrac)
                time.sleep(0.06)

        th: threading.Thread | None = None
        if overlay and words:
            overlay.speaking_chunk_words(words)
            th = threading.Thread(target=pump_sapi, args=(overlay,), daemon=True)
            th.start()
        engine.say(line)
        engine.runAndWait()
        stop.set()
        if th:
            th.join(timeout=0.3)
        if user_stop.is_set():
            raise SpeakingStopped()
        if overlay and words:
            overlay.speaking_tick(len(words) - 1, 1.0, 0.0)

        if i < len(segments) - 1 and pause_s > 0:
            t0 = time.monotonic()
            while time.monotonic() - t0 < pause_s:
                if overlay and overlay.poll_stop_speaking():
                    raise SpeakingStopped()
                time.sleep(0.1)


def speak_segments(segments: list[str], cfg: dict, overlay: OverlayController | None = None) -> None:
    if overlay:
        overlay.speaking()
    ok = False
    try:
        engine_name = str(cfg.get("tts_engine", "edge")).lower().strip()
        if engine_name == "sapi":
            try:
                speak_segments_sapi(segments, cfg, overlay=overlay)
                ok = True
            except SpeakingStopped:
                autostart_log("speaking stopped by user (overlay)")
                ok = True
            return
        try:
            import edge_tts  # noqa: F401
            import pygame  # noqa: F401
        except ImportError:
            print("edge-tts or pygame missing; install requirements or set tts_engine to sapi.", file=sys.stderr)
            try:
                speak_segments_sapi(segments, cfg, overlay=overlay)
                ok = True
            except SpeakingStopped:
                autostart_log("speaking stopped by user (overlay)")
                ok = True
            return

        try:
            asyncio.run(speak_segments_edge(segments, cfg, overlay=overlay))
            ok = True
        except SpeakingStopped:
            autostart_log("speaking stopped by user (overlay)")
            ok = True
        except Exception as e:
            autostart_log(f"Edge TTS / pygame failed: {e!r}")
            print(f"Edge TTS failed ({e}); falling back to Windows SAPI.", file=sys.stderr)
            try:
                speak_segments_sapi(segments, cfg, overlay=overlay)
                ok = True
                autostart_log("SAPI fallback finished")
            except SpeakingStopped:
                autostart_log("speaking stopped by user (overlay)")
                ok = True
            except Exception as e2:
                autostart_log(f"SAPI fallback also failed: {e2!r}")
                raise
    finally:
        if overlay and ok:
            overlay.briefing_done()


async def _print_edge_voices() -> None:
    import edge_tts

    voices = await edge_tts.list_voices()
    neural = [v for v in voices if "Neural" in v.get("ShortName", "")]
    for v in sorted(neural, key=lambda x: x["ShortName"]):
        loc = v.get("Locale", "")
        friendly = v.get("FriendlyName", "")
        print(f"  {v['ShortName']}")
        print(f"    {friendly} ({loc})\n")


def print_installed_voices() -> None:
    print("Microsoft Edge neural (recommended, tts_engine: edge) — set tts_voice to ShortName:\n")
    try:
        asyncio.run(_print_edge_voices())
    except Exception as e:
        print(f"  (Could not list Edge voices: {e})\n")

    print("Windows SAPI (tts_engine: sapi) — match tts_voice to part of name:\n")
    engine = pyttsx3.init()
    voices = engine.getProperty("voices") or []
    if not voices:
        print("  No SAPI voices reported.\n")
        return
    for v in voices:
        print(f"  {v.name}")
        print(f"    id: {v.id}\n")

