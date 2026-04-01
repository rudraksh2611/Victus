"""
Simple Tk setup form so users never edit JSON by hand.

Runs when config.json is missing or when --setup is passed.
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ..runtime_support import CONFIG_PATH, PROJECT_ROOT, example_config_path
from ..windows_autostart import register_logon_task, unregister_logon_task

# Common Edge neural voices (users can type any ShortName in the combo).
_EDGE_VOICE_PRESETS = (
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "hi-IN-SwaraNeural",
    "hi-IN-MadhurNeural",
)


def _load_defaults() -> dict[str, Any]:
    path = example_config_path()
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    fallback = PROJECT_ROOT / "config.example.json"
    if fallback.exists():
        with open(fallback, encoding="utf-8-sig") as f:
            return json.load(f)
    raise FileNotFoundError(
        "config.example.json not found. Reinstall the app or place config.example.json next to the program."
    )


def run_setup_wizard(*, editing: bool = False) -> bool:
    """
    Show modal setup window. Returns True if user saved, False if cancelled.
    """
    try:
        defaults = _load_defaults()
    except FileNotFoundError as e:
        # Last resort: Tk may not be up yet — stderr for frozen no-console builds is useless;
        # try messagebox after minimal root.
        root0 = tk.Tk()
        root0.withdraw()
        messagebox.showerror("Victus setup", str(e))
        root0.destroy()
        return False

    current: dict[str, Any] = {}
    if editing and CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            current = json.load(f)
    merged: dict[str, Any] = {**defaults, **{k: v for k, v in current.items() if k in defaults}}

    root = tk.Tk()
    root.title("Victus — setup")
    root.minsize(460, 420)
    root.resizable(True, True)
    try:
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    pad = {"padx": 10, "pady": 6}
    frm = ttk.Frame(root, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    intro = (
        "Fill in your details below. Nothing else is required — no code, no Notepad."
        if not editing
        else "Change your settings, then click Save."
    )
    ttk.Label(frm, text=intro, wraplength=420).pack(anchor="w", **pad)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="Your name (footer shows: Built by …)", width=28).pack(side=tk.LEFT)
    var_name = tk.StringVar(value=str(merged.get("overlay_credits_name", "")))
    ttk.Entry(row, textvariable=var_name, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="Greeting name (optional)", width=28).pack(side=tk.LEFT)
    var_greet = tk.StringVar(value=str(merged.get("greeting_name", "")))
    ttk.Entry(row, textvariable=var_greet, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="City (weather)", width=28).pack(side=tk.LEFT)
    var_city = tk.StringVar(value=str(merged.get("city", "")))
    ttk.Entry(row, textvariable=var_city, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="Voice (Edge)", width=28).pack(side=tk.LEFT)
    var_voice = tk.StringVar(value=str(merged.get("tts_voice", "en-IN-NeerjaNeural")))
    cb = ttk.Combobox(row, textvariable=var_voice, values=_EDGE_VOICE_PRESETS, width=38)
    cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="Briefing language", width=28).pack(side=tk.LEFT)
    var_lang = tk.StringVar(value=str(merged.get("briefing_language", "en")))
    ttk.Combobox(row, textvariable=var_lang, values=("en", "hi"), width=10, state="readonly").pack(side=tk.LEFT)

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, **pad)
    ttk.Label(row, text="News headlines count", width=28).pack(side=tk.LEFT)
    var_news = tk.StringVar(value=str(int(merged.get("news_count", 3))))
    sp = tk.Spinbox(row, from_=1, to=10, textvariable=var_news, width=8)
    sp.pack(side=tk.LEFT)

    var_overlay = tk.BooleanVar(value=bool(merged.get("show_overlay_ui", True)))
    ttk.Checkbutton(frm, text="Show small on-screen window during briefing", variable=var_overlay).pack(anchor="w", **pad)

    var_logon_autostart = tk.BooleanVar(value=bool(merged.get("windows_logon_autostart", True)))
    if sys.platform == "win32":
        ttk.Checkbutton(
            frm,
            text="Run when I sign in to Windows (scheduled task; recommended for the installed .exe)",
            variable=var_logon_autostart,
        ).pack(anchor="w", **pad)

    hint = (
        "You need internet for weather, news, and the voice. "
        "After saving, the briefing can start automatically."
    )
    ttk.Label(frm, text=hint, wraplength=420, foreground="#555").pack(anchor="w", pady=(8, 4))

    saved = False

    def do_save() -> None:
        nonlocal saved
        city = var_city.get().strip()
        voice = var_voice.get().strip()
        if not city:
            messagebox.showwarning("Victus setup", "Please enter a city for weather.")
            return
        if not voice:
            messagebox.showwarning("Victus setup", "Please choose or enter a voice name.")
            return
        try:
            nc = int(str(var_news.get()).strip())
        except ValueError:
            nc = 3
        nc = max(1, min(10, nc))

        out = dict(merged)
        out["overlay_credits_name"] = var_name.get().strip()
        out["greeting_name"] = var_greet.get().strip()
        out["city"] = city
        out["tts_voice"] = voice
        out["briefing_language"] = str(var_lang.get()).strip() or "en"
        out["news_count"] = nc
        out["show_overlay_ui"] = bool(var_overlay.get())
        out["tts_engine"] = "edge"
        if sys.platform == "win32":
            out["windows_logon_autostart"] = bool(var_logon_autostart.get())
        else:
            out["windows_logon_autostart"] = bool(merged.get("windows_logon_autostart", True))

        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        except OSError as e:
            messagebox.showerror("Victus setup", f"Could not save settings:\n{e}")
            return

        if sys.platform == "win32" and getattr(sys, "frozen", False):
            try:
                delay = int(float(out.get("logon_task_delay_seconds", 45)))
            except (TypeError, ValueError):
                delay = 45
            if out.get("windows_logon_autostart", True):
                ok_task, err_task = register_logon_task(delay_seconds=delay)
                if not ok_task:
                    messagebox.showwarning(
                        "Victus setup",
                        "Settings were saved, but Windows could not enable sign-in startup.\n"
                        "You may need to run the app once as a normal user with permission to create scheduled tasks.\n\n"
                        + (err_task or "Unknown error"),
                    )
            else:
                unregister_logon_task()

        saved = True
        messagebox.showinfo("Victus setup", "Settings saved.")
        root.destroy()

    def do_cancel() -> None:
        if not editing and not CONFIG_PATH.exists():
            if not messagebox.askyesno("Victus setup", "Exit without saving? You need settings to run the briefing."):
                return
        root.destroy()

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X, pady=(16, 0))
    ttk.Button(btn_row, text="Cancel", command=do_cancel).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_row, text="Save", command=do_save).pack(side=tk.RIGHT)

    root.protocol("WM_DELETE_WINDOW", do_cancel)
    root.mainloop()
    return saved


def main() -> None:
    """CLI entry: python -m victus.ui.setup_wizard"""
    ok = run_setup_wizard(editing=CONFIG_PATH.exists())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
