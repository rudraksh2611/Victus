
  VICTUS VOICE ASSISTANT — You're all set
  ────────────────────────────────────────

  WHAT JUST HAPPENED
  • Victus is installed in your user profile (no admin rights needed).
  • If you kept "Open the settings wizard", that window will appear so
    you can pick your city, name, voice, and language. Save and you're
    done — no JSON to edit.
  • If you kept "Start automatically when I sign in", a Windows
    Task Scheduler entry was registered. After your next sign-in,
    Victus will start on its own once the network and audio are ready.

  HOW TO USE IT
  • Hear a briefing now:
      Start menu → Victus Voice Assistant → Run briefing now
  • Change settings later:
      Start menu → Victus Voice Assistant → Change settings
      (or run VictusMorningBriefing.exe with --setup)
  • Stop a briefing in progress:
      Click the × on the small overlay near the bottom-right of the screen.

  TURNING AUTOSTART ON OR OFF LATER
  • Off: Open Task Scheduler (taskschd.msc), find "VictusMorningBriefing",
         and disable or delete it.
  • On:  Re-run setup, or use Start menu → Victus Voice Assistant →
         Windows integration guide for the manual command.

  IF SOMETHING GOES WRONG
  • Runtime log:
      %LOCALAPPDATA%\VictusVoiceAssistant\briefing.log
  • Reinstall over the top — your settings (config.json) are preserved.
  • Uninstall removes the app and the sign-in task; your saved settings
    file is left in place in case you want to re-use it.

  ────────────────────────────────────────
  Have a good morning. — Victus
