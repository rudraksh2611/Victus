# Victus Voice Assistant

Windows startup voice assistant that speaks a daily briefing after login:

- Time-aware greeting
- Current weather for your city
- Top India news headlines
- Smooth neural TTS with fallback support

It is designed for **automatic run at Windows sign-in** via Task Scheduler.

---

## How it is organized

- **`morning_briefing.py`** (repo root) is the only entry script. Task Scheduler should keep pointing at this path.
- Implementation lives in the **`victus/`** Python package (`import victus...`).
- **`config.json`** must sit in the **project root** (same folder as `morning_briefing.py`), not inside `victus/`.
- Run commands from the project root so imports and config resolution work.

---

## Features

- **Auto-start on login** with scheduled task scripts
- **Smart startup flow**
  - Optional login delay
  - Internet readiness checks
  - Optional post-network audio stabilization delay
- **News freshness handling**
  - Recent-first sorting
  - Headline deduplication
- **Speech engine options**
  - Edge Neural TTS (primary)
  - Windows SAPI (fallback)
- **Operational logging**
  - `%LOCALAPPDATA%\VictusVoiceAssistant\briefing.log`
- **Bottom-right overlay (Windows)**
  - Countdown during `login_delay_seconds`
  - “Connecting to network…” while waiting for internet
  - Speaking view: **code-style transcript on the left**, **waveform on the right**; **Built by Rudraksh** bottom-right
  - Toggle with `show_overlay_ui` in `config.json`

---

## Project structure

| Path | Role |
|------|------|
| `morning_briefing.py` | Thin entrypoint/orchestrator (stable path for Task Scheduler) |
| `victus/__init__.py` | Package marker and layout notes |
| `victus/runtime_support.py` | Config loading, logging, HTTP helpers (`config.json` resolved from project root) |
| `victus/startup_gate.py` | Login delay, optional mutex, internet polling, post-network delay |
| `victus/briefing/` | Briefing content: `content.py` (weather, RSS, segment builders); import as `victus.briefing` |
| `victus/speech/` | TTS: `engines.py` (Edge + pygame, SAPI fallback); import as `victus.speech` |
| `victus/ui/` | Optional bottom-right Tk overlay (separate process); import as `victus.ui` |
| `victus/briefing_content.py`, `speech_engines.py`, `overlay_ui.py` | Thin compatibility re-exports (old import paths still work) |
| `requirements.txt` | Python dependencies |
| `config.example.json` | Safe template; copy to `config.json` locally |
| `setup_login_task.ps1` | Register Windows scheduled task |
| `remove_login_task.ps1` | Remove the scheduled task |
| `TROUBLESHOOTING.txt` | Debugging guide |
| `.gitignore` | Excludes `.venv/`, `config.json`, logs, caches |

---

## Requirements

- Windows 10/11
- Python 3.10+
- Internet connection (for Edge TTS + weather/news APIs)

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

---

## Configuration

1. Copy template:

```powershell
copy config.example.json config.json
```

2. Edit `config.json` values.

### Config keys (reference)

| Key | Purpose |
|-----|---------|
| `show_overlay_ui` | If `true`, show the small bottom-right UI (countdown, then speaking animation). Set `false` to disable. |
| `overlay_canvas_width` | Width in pixels of the speaking waveform (default `340`). Change this to see a narrower or wider graphic; restart the app after editing. |
| `overlay_window_width` | Outer window width (default `420`, or `overlay_canvas_width + 80` if omitted). |
| `overlay_window_height` | Window height in pixels (default `248`). |
| `overlay_text_columns` | Width of the transcript text area in character columns (default `48`). |
| `city` | Weather location (e.g. `Greater Noida`) |
| `news_feed_url` | RSS feed URL for headlines |
| `news_count` | How many headlines to speak |
| `login_delay_seconds` | Wait after login before gating continues |
| `internet_wait_max_seconds` | Max time to wait for internet |
| `internet_check_poll_seconds` | Seconds between connectivity checks |
| `post_internet_delay_seconds` | Extra wait after internet is up (helps audio stack on login) |
| `logon_singleton_mutex` | If `true`, optional Windows mutex to reduce duplicate runs (usually `false`) |
| `tts_engine` | `edge` (neural) or `sapi` (offline Windows voices) |
| `tts_voice` | Edge `ShortName` or SAPI substring match |
| `edge_speaking_rate`, `edge_volume`, `edge_pitch` | Edge TTS tuning (rates like `+18%`) |
| `edge_playback_mode` | `continuous` (one long line) or `chunked` (per segment with short pauses) |
| `pause_between_sections_seconds` | Max pause between chunks (0–1 when using chunked Edge mode) |
| `sapi_voice_hint` | Hint for SAPI voice selection (e.g. `Zira`) |
| `tts_rate`, `tts_volume` | Used when `tts_engine` is `sapi` |
| `greeting_name` | Optional name after the time-based greeting |
| `briefing_language` | `en` or `hi` |

---

## Run manually

Normal run (uses delays and internet checks from `config.json`):

```powershell
.\.venv\Scripts\python.exe .\morning_briefing.py
```

Fast local test (skips login delay, internet wait, and post-internet delay):

```powershell
$env:VICTUS_NO_DELAY='1'
.\.venv\Scripts\python.exe .\morning_briefing.py
```

Optional: skip the logon mutex check when testing (only matters if `logon_singleton_mutex` is `true`):

```powershell
$env:VICTUS_SKIP_MUTEX='1'
```

List voices:

```powershell
.\.venv\Scripts\python.exe .\morning_briefing.py --list-voices
```

---

## Enable auto-run at login

Register task:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_login_task.ps1
```

Remove task:

```powershell
powershell -ExecutionPolicy Bypass -File .\remove_login_task.ps1
```

Task name used: `VictusMorningBriefing`

---

## Troubleshooting

- Use runtime log:
  - `%LOCALAPPDATA%\VictusVoiceAssistant\briefing.log`
- Read full guide:
  - `TROUBLESHOOTING.txt`

Common checks:

- Confirm Task Scheduler task is enabled
- Verify `config.json` exists and is valid JSON
- Verify internet is available at login
- Ensure system output audio device is active

---

## Security notes

Do **not** commit personal/local files:

- `config.json`
- `.venv/`
- Local logs

Use `config.example.json` as the shared template.
