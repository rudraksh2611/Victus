from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

import pyttsx3

from .briefing_content import soften_for_speech
from .runtime_support import autostart_log, cfg_float


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


async def speak_edge_chunked(segments: list[str], voice: str, rate: str, volume: str, pitch: str, pause_s: float) -> None:
    import edge_tts
    import pygame

    pause_s = min(max(0.0, pause_s), 1.0)
    lines = [t for t in (soften_for_speech(s.strip()) for s in segments if s.strip()) if t]
    if not lines:
        return

    init_pygame_mixer_with_retries()

    async def synth(text: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="victus_")
        os.close(fd)
        comm = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume, pitch=pitch)
        await comm.save(path)
        return path

    current_path = await synth(lines[0])
    for i in range(len(lines)):
        pygame.mixer.music.load(current_path)
        pygame.mixer.music.play()

        next_task: asyncio.Task[str] | None = None
        if i + 1 < len(lines):
            next_task = asyncio.create_task(synth(lines[i + 1]))

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.02)
        if pause_s > 0:
            await asyncio.sleep(pause_s)

        try:
            os.remove(current_path)
        except OSError:
            pass

        if next_task is not None:
            current_path = await next_task


async def speak_segments_edge(segments: list[str], cfg: dict) -> None:
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
        await speak_edge_chunked(nonempty, voice, rate, volume, pitch, pause_s)
        return

    line = " ".join(soften_for_speech(s) for s in nonempty if s.strip())
    if line:
        await speak_edge_chunked([line], voice, rate, volume, pitch, 0)


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


def speak_segments_sapi(segments: list[str], cfg: dict) -> None:
    rate = int(cfg.get("tts_rate", 200))
    pause_s = cfg_float(cfg, "pause_between_sections_seconds", 0, 0.0, 1.0)
    vol = cfg.get("tts_volume")
    voice_hint = sapi_voice_hint(cfg)

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
        engine.say(text.strip())
        engine.runAndWait()
        if i < len(segments) - 1 and pause_s > 0:
            time.sleep(pause_s)


def speak_segments(segments: list[str], cfg: dict) -> None:
    engine_name = str(cfg.get("tts_engine", "edge")).lower().strip()
    if engine_name == "sapi":
        speak_segments_sapi(segments, cfg)
        return
    try:
        import edge_tts  # noqa: F401
        import pygame  # noqa: F401
    except ImportError:
        print("edge-tts or pygame missing; install requirements or set tts_engine to sapi.", file=sys.stderr)
        speak_segments_sapi(segments, cfg)
        return

    try:
        asyncio.run(speak_segments_edge(segments, cfg))
    except Exception as e:
        autostart_log(f"Edge TTS / pygame failed: {e!r}")
        print(f"Edge TTS failed ({e}); falling back to Windows SAPI.", file=sys.stderr)
        try:
            speak_segments_sapi(segments, cfg)
            autostart_log("SAPI fallback finished")
        except Exception as e2:
            autostart_log(f"SAPI fallback also failed: {e2!r}")
            raise


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

