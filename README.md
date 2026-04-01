# Victus Voice Assistant

Windows startup voice assistant that speaks a daily briefing after login:

- Time-aware greeting
- Current weather for your city
- Top India news headlines
- Edge neural TTS with SAPI fallback
- Optional bottom-right overlay UI

Designed for **automatic run at Windows sign-in** via Task Scheduler.

---

## How it is organized

- **`morning_briefing.py`** (repo root) is the stable entry script.
- Implementation lives in the **`victus/`** package (`import victus...`).
- **`config.json`** must live in the **project root** (same folder as `morning_briefing.py`).

---

## Features

- **Auto-start on login** via scheduled task scripts
- **Boot reliability flow**
  - Scheduled task startup delay (`DelayAfterLogonSeconds`)
  - Internet readiness checks
  - Post-network audio stabilization delay
  - Extra autostart-only delays (`VICTUS_AUTOSTART=1` path)
- **Speech engine options**
  - Edge neural (`tts_engine: edge`)
  - Windows SAPI fallback (`tts_engine: sapi`)
- **Overlay UI (Windows, optional)**
  - Countdown during startup delay
  - Network wait state
  - Speaking transcript + waveform
  - Stop / close controls
- **Operational logging**
  - `%LOCALAPPDATA%\VictusVoiceAssistant\briefing.log`

---

## Project structure

| Path | Role |
|------|------|
| `morning_briefing.py` | Thin entrypoint/orchestrator |
| `victus/runtime_support.py` | Config loading, logging, HTTP helpers, autostart env detection |
| `victus/startup_gate.py` | Login delay, internet wait, mutex check, post-network delay |
| `victus/briefing/` | Weather/news fetch and briefing segment building |
| `victus/speech/` | Edge + pygame playback, SAPI fallback |
| `victus/ui/` | Tk overlay process + parent controller |
| `victus/briefing_content.py`, `victus/speech_engines.py`, `victus/overlay_ui.py` | Compatibility re-export shims |
| `config.example.json` | Safe template; copy to `config.json` locally |
| `setup_login_task.ps1` | Registers the logon task with delay |
| `launch_at_logon.ps1` | Launcher used by the task (sets `VICTUS_AUTOSTART=1`) |
| `remove_login_task.ps1` | Removes scheduled task |
| `TROUBLESHOOTING.txt` | Boot/runtime troubleshooting guide |

---

## Requirements

- Windows 10/11
- Python 3.10+
- Internet connection (weather/news + Edge TTS)

Install:

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

2. Edit `config.json`.

### Config keys (reference)

| Key | Purpose |
|-----|---------|
| `show_overlay_ui` | Enable/disable bottom-right overlay window |
| `overlay_wave_height` | Speaking waveform circle diameter (px) |
| `overlay_window_width` | Overlay window width (px) |
| `overlay_window_height` | Overlay window height (px) |
| `overlay_text_columns` | Transcript width in character columns |
| `overlay_text_height_lines` | Transcript height in lines |
| `overlay_code_font_size` | Transcript font size |
| `overlay_child_process_ready_seconds` | Wait after spawning overlay process |
| `city` | Weather city name |
| `news_feed_url` | RSS URL for headlines |
| `news_count` | Number of headlines |
| `pre_overlay_delay_seconds` | Delay before overlay for all runs |
| `autostart_extra_delay_seconds` | Extra pre-overlay delay when autostarted |
| `login_delay_seconds` | Countdown delay before startup gates continue |
| `internet_wait_max_seconds` | Max wait for internet |
| `internet_check_poll_seconds` | Poll interval for internet checks |
| `post_internet_delay_seconds` | Delay after internet becomes reachable |
| `autostart_post_internet_extra_seconds` | Extra post-internet delay when autostarted |
| `logon_singleton_mutex` | Optional mutex to avoid duplicate logon starts |
| `tts_engine` | `edge` or `sapi` |
| `tts_voice` | Edge `ShortName` (or SAPI hint path if using SAPI) |
| `edge_speaking_rate`, `edge_volume`, `edge_pitch` | Edge TTS tuning |
| `edge_playback_mode` | `chunked` or `continuous` |
| `sapi_voice_hint` | SAPI voice hint (e.g. `Zira`) |
| `tts_rate`, `tts_volume` | SAPI speech settings |
| `pause_between_sections_seconds` | Pause between section clips |
| `greeting_name` | Optional name for greeting |
| `briefing_language` | Briefing language (`en` / `hi`) |

---

## Run manually

Normal run:

```powershell
.\.venv\Scripts\python.exe .\morning_briefing.py
```

Fast local test (skip startup waits):

```powershell
$env:VICTUS_NO_DELAY='1'
.\.venv\Scripts\python.exe .\morning_briefing.py
```

List available voices:

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

Task name: `VictusMorningBriefing`

Notes:

- `setup_login_task.ps1` sets a startup delay (`DelayAfterLogonSeconds`, currently 45).
- Task runs `launch_at_logon.ps1`, which sets `VICTUS_AUTOSTART=1` and starts `morning_briefing.py`.

---

## Troubleshooting

- Log file: `%LOCALAPPDATA%\VictusVoiceAssistant\briefing.log`
- Full guide: `TROUBLESHOOTING.txt`

---

## Security notes

Do **not** commit local/personal runtime files:

- `config.json`
- `.venv/`
- local logs

Use `config.example.json` as the shared template.
