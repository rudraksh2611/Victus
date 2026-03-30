"""
Bottom-right desktop overlay: countdown, then Siri-style speaking animation.

Runs in a separate process so Tk does not block TTS/network work in the parent.
"""
from __future__ import annotations

import math
import multiprocessing
import queue as std_queue
import sys
import time
from multiprocessing import Process
from typing import Any

# ---------------------------------------------------------------------------
# Child process: must be picklable for Windows "spawn" — keep at module level.
# ---------------------------------------------------------------------------


def _geom_from_cfg(cfg: dict) -> dict:
    """Sizes for the overlay window and speaking canvas (read from config.json)."""
    text_cols = int(cfg.get("overlay_text_columns", 48))
    text_cols = max(20, min(text_cols, 80))
    text_lines = int(cfg.get("overlay_text_height_lines", 4))
    text_lines = max(3, min(text_lines, 12))
    code_font_size = int(cfg.get("overlay_code_font_size", 9))
    code_font_size = max(7, min(code_font_size, 12))
    # Circular speaking graphic: square canvas side = overlay_wave_height (diameter)
    wave_h = int(cfg.get("overlay_wave_height", 64))
    wave_h = max(48, min(wave_h, 120))
    circle_d = wave_h
    if cfg.get("overlay_window_width") is not None:
        win_w = int(cfg["overlay_window_width"])
    else:
        # Left: transcript rectangle | Right: circle (diameter = circle_d)
        win_w = max(420, circle_d + 24 + int(text_cols * 7.2))
    win_w = max(380, min(win_w, 900))
    win_h = int(cfg.get("overlay_window_height", 248))
    win_h = max(200, min(win_h, 800))
    return {
        "canvas_w": circle_d,
        "win_w": win_w,
        "win_h": win_h,
        "text_cols": text_cols,
        "text_lines": text_lines,
        "code_font_size": code_font_size,
        "wave_h": wave_h,
    }


def _overlay_main(
    cmd_queue: multiprocessing.Queue,
    feedback_queue: multiprocessing.Queue,
    geom: dict | None = None,
) -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    geom = geom or {}
    win_w = int(geom.get("win_w", 420))
    win_h = int(geom.get("win_h", 248))
    circle_d = int(geom.get("canvas_w", 64))
    text_cols = int(geom.get("text_cols", 48))
    text_lines = int(geom.get("text_lines", 4))
    code_font_size = int(geom.get("code_font_size", 9))

    root = tk.Tk()
    root.title("Victus")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.94)
    except tk.TclError:
        pass

    w, h = win_w, win_h
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    margin = 16
    x = max(0, sw - w - margin)
    y = max(0, sh - h - margin - 48)
    root.geometry(f"{w}x{h}+{x}+{y}")

    bg = "#1c1c1e"
    root.configure(bg=bg)

    outer = tk.Frame(root, bg=bg, padx=12, pady=14)
    outer.pack(fill=tk.BOTH, expand=True)

    title_font = tkfont.Font(family="Segoe UI", size=11, weight="normal")
    big_font = tkfont.Font(family="Segoe UI Semibold", size=44, weight="bold")
    sub_font = tkfont.Font(family="Segoe UI", size=10)

    title_row = tk.Frame(outer, bg=bg)
    title_row.pack(fill=tk.X)

    def on_close_speaking() -> None:
        try:
            feedback_queue.put_nowait({"cmd": "stop_speaking"})
        except Exception:
            pass
        try:
            close_spk_btn.config(state=tk.DISABLED)
        except tk.TclError:
            pass

    close_spk_btn = tk.Button(
        title_row,
        text="×",
        font=title_font,
        fg="#fca5a5",
        bg=bg,
        activebackground="#3f3f46",
        activeforeground="#ffffff",
        borderwidth=0,
        highlightthickness=0,
        relief=tk.FLAT,
        cursor="hand2",
        padx=2,
        pady=0,
        command=on_close_speaking,
    )
    title_lbl = tk.Label(title_row, text="Victus", fg="#8e8e93", bg=bg, font=title_font, anchor="w")
    title_lbl.pack(side=tk.LEFT, padx=(2, 0))

    body = tk.Frame(outer, bg=bg)
    body.pack(fill=tk.BOTH, expand=True)

    speaking_split = tk.Frame(body, bg=bg)

    footer_font = tkfont.Font(family="Segoe UI", size=8)
    footer_lbl = tk.Label(outer, text="Built by Rudraksh, yeah it's me", fg="#636366", bg=bg, font=footer_font, anchor="e")

    # Countdown / status text
    num_lbl = tk.Label(body, text="25", fg="white", bg=bg, font=big_font)
    sub_lbl = tk.Label(body, text="Starting briefing", fg="#aeaeb2", bg=bg, font=sub_font)

    def on_stop_briefing() -> None:
        try:
            feedback_queue.put_nowait({"cmd": "cancel"})
        except Exception:
            pass
        try:
            stop_btn.config(state=tk.DISABLED)
            sub_lbl.config(text="Stopping…", fg="#f87171")
        except tk.TclError:
            pass

    stop_btn = tk.Button(
        body,
        text="Stop",
        command=on_stop_briefing,
        fg="#ffffff",
        bg="#48484a",
        activebackground="#5c5c5e",
        activeforeground="#ffffff",
        font=sub_font,
        padx=14,
        pady=5,
        cursor="hand2",
        relief=tk.FLAT,
        highlightthickness=0,
    )

    # Speaking: transcript (left) + circular waveform (right)
    code_font = tkfont.Font(family="Consolas", size=code_font_size)
    code_font_b = tkfont.Font(family="Consolas", size=code_font_size, weight="bold")
    text_w = tk.Text(
        speaking_split,
        height=text_lines,
        width=text_cols,
        wrap=tk.WORD,
        bg="#0d1117",
        fg="#7dd3fc",
        font=code_font,
        relief=tk.FLAT,
        padx=4,
        pady=4,
        highlightthickness=1,
        highlightbackground="#30363d",
        highlightcolor="#30363d",
        borderwidth=0,
        cursor="",
        takefocus=0,
        insertbackground="#7dd3fc",
    )
    text_w.tag_configure("dim", foreground="#7dd3fc", font=code_font)
    text_w.tag_configure("hi", foreground="#4ade80", font=code_font_b)
    text_w.tag_configure("cursor", foreground="#22d3ee", font=code_font_b)
    text_w.tag_configure("err", foreground="#fca5a5", font=code_font)

    # Right: square frame containing a circular speaking graphic (see draw_siri_waveform)
    wave_wrap = tk.Frame(speaking_split, width=circle_d, height=circle_d, bg=bg)
    wave_wrap.pack_propagate(False)
    canvas = tk.Canvas(wave_wrap, width=circle_d, height=circle_d, bg=bg, highlightthickness=0)
    canvas.pack(anchor="center")
    cw = circle_d

    state: dict[str, Any] = {
        "phase": "countdown",
        "remaining": 25,
        "anim_t": 0.0,
        "after_id": None,
        "words": [],
        "widx": 0,
        "wf": 0.0,
        "p": 0.0,
        "line_target": "",
        "typed_char_count": 0,
    }

    def clear_body() -> None:
        num_lbl.pack_forget()
        sub_lbl.pack_forget()
        stop_btn.pack_forget()
        canvas.pack_forget()
        wave_wrap.pack_forget()
        text_w.pack_forget()
        speaking_split.pack_forget()
        try:
            close_spk_btn.pack_forget()
            close_spk_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        try:
            title_lbl.pack_forget()
            title_lbl.pack(side=tk.LEFT, padx=(2, 0), anchor="w")
        except tk.TclError:
            pass

    def show_countdown(n: int) -> None:
        clear_body()
        state["phase"] = "countdown"
        num_lbl.config(text=str(max(0, int(n))))
        sub_lbl.config(text="Starting briefing", fg="#aeaeb2")
        try:
            stop_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        num_lbl.pack(pady=(4, 0))
        sub_lbl.pack()
        stop_btn.pack(pady=(10, 0))

    def show_waiting_net() -> None:
        clear_body()
        state["phase"] = "waiting_net"
        num_lbl.config(text="")
        sub_lbl.config(text="Connecting to network…", fg="#aeaeb2")
        try:
            stop_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        sub_lbl.pack(pady=(18, 0))
        stop_btn.pack(pady=(12, 0))

    def show_preparing() -> None:
        clear_body()
        state["phase"] = "preparing"
        sub_lbl.config(text="Preparing audio…", fg="#aeaeb2")
        try:
            stop_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        sub_lbl.pack(pady=(18, 0))
        stop_btn.pack(pady=(12, 0))

    def show_error(err_text: str) -> None:
        """Same Text widget as the transcript; waveform hidden."""
        if state.get("after_id"):
            try:
                root.after_cancel(state["after_id"])
            except Exception:
                pass
            state["after_id"] = None
        clear_body()
        state["phase"] = "error"
        sub_lbl.config(text="Something went wrong", fg="#f87171")
        sub_lbl.pack(pady=(0, 4))
        speaking_split.pack(fill=tk.BOTH, expand=True)
        text_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0))
        text_w.delete("1.0", tk.END)
        text_w.insert(tk.END, (err_text or "(unknown error)").strip(), "err")
        try:
            text_w.see("1.0")
        except tk.TclError:
            pass

    _MAX_VISIBLE_WORDS = 52

    def build_line_target() -> str:
        """Full text that should appear for the current speech position (incl. partial word)."""
        words = state.get("words") or []
        if not words:
            return ""
        widx = int(state.get("widx", 0))
        wf = float(state.get("wf", 0.0))
        prog = float(state.get("p", 0.0))
        widx = max(0, min(widx, len(words) - 1))
        on_last_word = widx >= len(words) - 1
        if len(words) <= _MAX_VISIBLE_WORDS:
            disp = words
            offset = 0
        else:
            half = _MAX_VISIBLE_WORDS // 2
            lo = max(0, min(widx - half, len(words) - _MAX_VISIBLE_WORDS))
            disp = words[lo : lo + _MAX_VISIBLE_WORDS]
            offset = lo
        prefix = "… " if offset > 0 else ""
        suffix = " …" if offset + len(disp) < len(words) else ""
        rel_ix = max(0, min(widx - offset, len(disp) - 1))
        parts: list[str] = []
        for i in range(rel_ix):
            parts.append(disp[i])
        cur = disp[rel_ix]
        # Full word: high wf, or playback finished (last tick sends wf=0, p=1)
        if wf >= 0.99 or (on_last_word and prog >= 0.999):
            parts.append(cur)
        else:
            n = min(len(cur), max(0, math.ceil(len(cur) * float(wf) - 1e-12)))
            if n == 0 and len(cur) > 0:
                n = 1
            parts.append(cur[:n])
        line_body = " ".join(parts)
        return prefix + line_body + suffix

    def sync_line_target() -> None:
        state["line_target"] = build_line_target()
        lt = state.get("line_target", "")
        # Keep transcript aligned with speech (no lag vs audio)
        state["typed_char_count"] = len(lt)

    def advance_typewriter() -> None:
        """Kept for compatibility; display is synced in sync_line_target."""
        return

    def refresh_typed_display() -> None:
        text_w.delete("1.0", tk.END)
        target = state.get("line_target", "")
        tc = int(state.get("typed_char_count", 0))
        if not target and not (state.get("words") or []):
            text_w.insert(tk.END, "…", "dim")
            return
        vis = target[:tc]
        if not vis.strip():
            return
        # Keep last part of long text visible (wrap hides earlier lines in small box)
        max_chars = max(32, text_cols * text_lines * 2)
        if len(vis) > max_chars:
            vis = "… " + vis[-(max_chars - 2) :].lstrip()
        # Last token highlighted; preserve exact spacing (no split/join)
        last_sp = vis.rfind(" ")
        if last_sp == -1:
            text_w.insert(tk.END, vis, "hi")
        else:
            text_w.insert(tk.END, vis[: last_sp + 1], "dim")
            text_w.insert(tk.END, vis[last_sp + 1 :], "hi")
        blink = (int(state.get("anim_t", 0) * 12) % 2) == 0
        at_end = bool(target) and tc >= len(target)
        if tc < len(target) or (at_end and blink):
            text_w.insert(tk.END, " ▌" if blink else " ▎", "cursor")
        try:
            text_w.see(tk.END)
        except tk.TclError:
            pass

    def draw_siri_waveform() -> None:
        canvas.delete("all")
        t = state["anim_t"]
        words = state.get("words") or []
        d = float(cw)
        pad = 3.0
        cx = d * 0.5
        cy = d * 0.5
        r_face = d * 0.5 - pad

        canvas.create_oval(
            pad,
            pad,
            d - pad,
            d - pad,
            fill="#16131f",
            outline="#52525b",
            width=2,
        )
        canvas.create_oval(
            pad + 4,
            pad + 4,
            d - pad - 4,
            d - pad - 4,
            outline="#3f3f46",
            width=1,
        )

        if words:
            cent = (state.get("widx", 0) + float(state.get("wf", 0.0))) / max(len(words), 1)
            cent = max(0.04, min(0.96, cent))
            pulse = 0.72 + 0.28 * math.sin(t * 2.6)
        else:
            cent = 0.5 + 0.09 * math.sin(t * 0.88)
            pulse = 0.55 + 0.45 * math.sin(t * 1.4)

        r_draw = max(8.0, r_face - 8.0)
        x_min = cx - r_draw * 0.88
        x_max = cx + r_draw * 0.88
        x_span = max(x_max - x_min, 1.0)
        # Slightly taller vertical scale so spikes read clearly in the circle
        sc = max(0.58, min(1.28, r_face / 34.0))
        base_amp = r_draw * 0.50

        def envelope(nx: float) -> float:
            if words:
                e = math.exp(-0.5 * ((nx - cent) ** 2) / 0.095)
                e = max(0.07, min(1.0, e * 1.18))
                e *= 0.76 + 0.24 * math.sin(t * 3.1 + nx * 7.2)
                return e * pulse
            e = 0.34 + 0.66 * (0.5 + 0.5 * math.sin(t * 1.45 + nx * 5.2))
            return e * (0.85 + 0.15 * math.sin(t * 2.0 + nx * 3.0))

        def wave_y(nx: float, phase: float, freq: float, amp: float) -> float:
            env = envelope(nx)
            w = math.sin(nx * freq * math.pi * 2 + 6.2 * nx + t * 2.55 + phase)
            w += 0.32 * math.sin(nx * freq * math.pi * 4 + 3.8 * nx + t * 3.05 + phase * 1.2)
            w += 0.12 * math.sin(nx * 18.0 + t * 4.2)
            return cy + amp * sc * env * w

        xi0 = int(x_min)
        xi1 = int(x_max) + 1

        def stroke(phase: float, freq: float, amp: float, color: str, width: int) -> None:
            pts: list[float] = []
            for x in range(xi0, xi1, 1):
                nx = (float(x) - x_min) / x_span
                y = wave_y(nx, phase, freq, amp)
                dx = float(x) - cx
                dy = y - cy
                dist = math.hypot(dx, dy)
                if dist > r_face - 0.5 and dist > 1e-6:
                    s = (r_face - 0.5) / dist
                    y = cy + dy * s
                pts.extend([float(x), y])
            try:
                canvas.create_line(pts, fill=color, width=width, smooth=True, splinesteps=16, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            except tk.TclError:
                canvas.create_line(pts, fill=color, width=width)

        stroke(0.0, 3.05, base_amp * 0.78, "#1e0b3a", max(6, int(11 * sc)))
        stroke(0.4, 3.12, base_amp * 0.72, "#581c87", max(5, int(8 * sc)))
        stroke(1.1, 2.88, base_amp * 0.66, "#a21caf", max(5, int(7 * sc)))
        stroke(1.85, 2.72, base_amp * 0.62, "#0891b2", max(4, int(6 * sc)))
        stroke(0.9, 3.0, base_amp * 0.52, "#e879f9", max(3, int(4 * sc)))
        stroke(0.55, 3.08, base_amp * 0.44, "#f0f9ff", max(2, int(3 * sc)))

        state["anim_t"] += 0.085

    def animate_speaking() -> None:
        if state["phase"] != "speaking":
            return
        sync_line_target()
        advance_typewriter()
        refresh_typed_display()
        draw_siri_waveform()
        state["after_id"] = root.after(33, animate_speaking)

    def show_speaking() -> None:
        clear_body()
        state["phase"] = "speaking"
        state["anim_t"] = 0.0
        state["widx"] = 0
        state["wf"] = 0.0
        state["p"] = 0.0
        state["line_target"] = ""
        state["typed_char_count"] = 0
        sub_lbl.config(text="Voice assistant", fg="#ffffff")
        sub_lbl.pack(pady=(0, 2))
        speaking_split.pack(fill=tk.BOTH, expand=True)
        text_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        wave_wrap.pack(side=tk.RIGHT, anchor=tk.CENTER)
        canvas.pack(anchor="center")
        try:
            title_lbl.pack_forget()
            close_spk_btn.pack(side=tk.LEFT, anchor="nw")
            title_lbl.pack(side=tk.LEFT, padx=(6, 0), anchor="w")
        except tk.TclError:
            pass
        if state["after_id"]:
            try:
                root.after_cancel(state["after_id"])
            except Exception:
                pass
        animate_speaking()

    def apply_speaking_chunk(msg: dict) -> None:
        if state.get("phase") == "error":
            return
        raw = msg.get("words") or []
        if isinstance(raw, str):
            words = raw.split()
        else:
            words = list(raw)
        if state["phase"] != "speaking":
            show_speaking()
        state["words"] = words
        state["widx"] = 0
        state["wf"] = 0.0
        state["p"] = 0.0
        state["typed_char_count"] = 0
        sync_line_target()

    def apply_speaking_tick(msg: dict) -> None:
        if state.get("phase") == "error":
            return
        words = state.get("words") or []
        nw = int(msg.get("idx", 0))
        if words:
            nw = max(0, min(nw, len(words) - 1))
        state["widx"] = nw
        state["wf"] = float(msg.get("wf", 0.0))
        state["p"] = float(msg.get("p", 0.0))
        if state["phase"] != "speaking":
            show_speaking()
        sync_line_target()

    def show_done() -> None:
        if state["after_id"]:
            try:
                root.after_cancel(state["after_id"])
            except Exception:
                pass
            state["after_id"] = None
        clear_body()
        state["phase"] = "done"
        sub_lbl.config(text="Briefing complete", fg="#8e8e93")
        sub_lbl.pack(pady=(22, 0))

    def apply_msg(msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "countdown":
            show_countdown(int(msg.get("remaining", 0)))
        elif cmd == "phase":
            ph = str(msg.get("phase", ""))
            if ph == "waiting_net":
                show_waiting_net()
            elif ph == "preparing":
                show_preparing()
            elif ph == "speaking":
                show_speaking()
            elif ph == "done":
                show_done()
        elif cmd == "error":
            show_error(str(msg.get("text", "")))
        elif cmd == "quit":
            root.quit()

    def poll_queue() -> None:
        try:
            batch: list[dict] = []
            while True:
                batch.append(cmd_queue.get_nowait())
        except std_queue.Empty:
            pass
        if not batch:
            root.after(16, poll_queue)
            return
        for m in batch:
            if m.get("cmd") == "quit":
                apply_msg(m)
                return
        err_msgs = [m for m in batch if m.get("cmd") == "error"]
        if err_msgs:
            apply_msg(err_msgs[-1])
        for m in batch:
            c = m.get("cmd")
            if c in ("speaking_chunk", "speaking_tick", "error", "quit"):
                continue
            apply_msg(m)
        chunk_msg: dict | None = None
        last_tick: dict | None = None
        for m in batch:
            c = m.get("cmd")
            if c == "speaking_chunk":
                chunk_msg = m
            elif c == "speaking_tick":
                last_tick = m
        if chunk_msg is not None:
            apply_speaking_chunk(chunk_msg)
        if last_tick is not None:
            apply_speaking_tick(last_tick)
        root.after(16, poll_queue)

    footer_lbl.pack(fill=tk.X, pady=(8, 0))
    show_countdown(25)
    root.after(100, poll_queue)
    root.mainloop()
    root.destroy()


# ---------------------------------------------------------------------------
# Parent-side controller
# ---------------------------------------------------------------------------


class OverlayController:
    """Starts the overlay process and sends non-blocking UI updates."""

    def __init__(self, cfg: dict) -> None:
        self._enabled = bool(cfg.get("show_overlay_ui", True)) and overlay_supported()
        self._geom = _geom_from_cfg(cfg)
        self._proc: Process | None = None
        self._q: multiprocessing.Queue | None = None
        self._feedback_q: multiprocessing.Queue | None = None
        self._pending_cancel = False
        self._pending_stop_speaking = False

    def start(self) -> None:
        if not self._enabled:
            return
        from ..runtime_support import autostart_log

        autostart_log(f"overlay starting geom={self._geom}")
        ctx = multiprocessing.get_context("spawn")
        self._q = ctx.Queue()
        self._feedback_q = ctx.Queue()
        self._proc = ctx.Process(
            target=_overlay_main,
            args=(self._q, self._feedback_q, self._geom),
            daemon=True,
        )
        self._proc.start()
        time.sleep(0.35)

    def _send(self, msg: dict) -> None:
        if not self._enabled or self._q is None:
            return
        try:
            self._q.put_nowait(msg)
        except Exception:
            pass

    def _drain_feedback(self) -> None:
        if not self._enabled or self._feedback_q is None:
            return
        try:
            while True:
                m = self._feedback_q.get_nowait()
                c = m.get("cmd")
                if c == "cancel":
                    self._pending_cancel = True
                elif c == "stop_speaking":
                    self._pending_stop_speaking = True
        except std_queue.Empty:
            pass

    def poll_cancel(self) -> bool:
        """True if the user pressed Stop in the overlay (countdown / early startup)."""
        self._drain_feedback()
        if self._pending_cancel:
            self._pending_cancel = False
            return True
        return False

    def poll_stop_speaking(self) -> bool:
        """True if the user pressed × during the speaking phase (stop TTS)."""
        self._drain_feedback()
        if self._pending_stop_speaking:
            self._pending_stop_speaking = False
            return True
        return False

    def countdown_tick(self, remaining: int) -> None:
        self._send({"cmd": "countdown", "remaining": remaining})

    def waiting_network(self) -> None:
        self._send({"cmd": "phase", "phase": "waiting_net"})

    def preparing_audio(self) -> None:
        self._send({"cmd": "phase", "phase": "preparing"})

    def speaking(self) -> None:
        self._send({"cmd": "phase", "phase": "speaking"})

    def speaking_chunk_words(self, words: list[str]) -> None:
        """Send full word list once per TTS clip (avoids flooding the UI queue)."""
        self._send({"cmd": "speaking_chunk", "words": words})

    def speaking_tick(self, idx: int, progress: float, wfrac: float = 0.0) -> None:
        """Lightweight highlight position (~20 Hz); pairs with speaking_chunk_words."""
        self._send({"cmd": "speaking_tick", "idx": idx, "p": progress, "wf": wfrac})

    def show_error(self, message: str) -> None:
        """Show exception text in the same transcript area as the briefing."""
        if not self._enabled:
            return
        raw = (message or "Unknown error").strip()
        cap = 12000
        text = raw if len(raw) <= cap else raw[:cap] + "\n…(truncated)"
        self._send({"cmd": "error", "text": text})

    def briefing_done(self) -> None:
        """Short 'complete' state then close."""
        self._send({"cmd": "phase", "phase": "done"})
        time.sleep(1.2)
        self.quit()

    def quit(self) -> None:
        self._send({"cmd": "quit"})
        if self._proc and self._proc.is_alive():
            self._proc.join(timeout=3.0)

    def shutdown_quick(self) -> None:
        """Close overlay without 'complete' animation (errors / duplicate instance)."""
        self._send({"cmd": "quit"})
        if self._proc and self._proc.is_alive():
            self._proc.join(timeout=2.0)


def overlay_supported() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True
