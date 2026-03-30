# Victus Voice Assistant

Windows startup voice assistant that speaks a daily briefing after login:
- Time-aware greeting
- Current weather for your city
- Top India news headlines
- Smooth neural TTS with fallback support

It is designed for **automatic run at Windows sign-in** via Task Scheduler.

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

---

## Project Structure

- `morning_briefing.py` - entrypoint/orchestrator (kept stable for Task Scheduler)
- `runtime_support.py` - config loading, logging, HTTP helper functions
- `startup_gate.py` - login/internet/mutex startup gating logic
- `briefing_content.py` - weather/news retrieval and briefing text construction
- `speech_engines.py` - Edge/SAPI TTS + playback handling
- `setup_login_task.ps1` - register Windows scheduled task
- `remove_login_task.ps1` - remove the scheduled task
- `config.example.json` - safe template config
- `TROUBLESHOOTING.txt` - troubleshooting guide

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

### Important Config Keys

- `city` - weather location (example: `Greater Noida`)
- `news_feed_url` - RSS source for headlines
- `news_count` - number of spoken headlines
- `login_delay_seconds` - fixed delay after login
- `internet_wait_max_seconds` - max wait for internet availability
- `internet_check_poll_seconds` - internet probe interval
- `post_internet_delay_seconds` - delay after internet is up (audio stack stabilization)
- `tts_engine` - `edge` or `sapi`
- `tts_voice` - voice id / name for selected engine
- `edge_speaking_rate` - speaking speed for Edge TTS
- `edge_playback_mode` - `continuous` or `chunked`
- `greeting_name` - optional name in greeting
- `briefing_language` - `en` or `hi`

---

## Run Manually

Normal run:

```powershell
.\.venv\Scripts\python.exe .\morning_briefing.py
```

Fast local test (skip startup waits):

```powershell
$env:VICTUS_NO_DELAY='1'
.\.venv\Scripts\python.exe .\morning_briefing.py
```

List voices:

```powershell
.\.venv\Scripts\python.exe .\morning_briefing.py --list-voices
```

---

## Enable Auto-Run at Login

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

## Security Notes

- Do **not** commit personal/local files:
  - `config.json`
  - `.venv/`
  - local logs
- Use `config.example.json` as the shared template.

