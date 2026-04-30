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

from ..runtime_support import cfg_float

# ---------------------------------------------------------------------------
# Color palette — kept in one place so the look stays consistent.
# ---------------------------------------------------------------------------

_BG_OUTER = "#0c0c10"
_BG_CARD = "#17171c"
_BG_CARD_INNER = "#1c1c22"
_BORDER = "#2a2a33"
_ACCENT = "#7c3aed"
_ACCENT_SOFT = "#4c1d95"
_ACCENT_CYAN = "#22d3ee"
_ACCENT_PINK = "#c026d3"
_TEXT = "#f4f4f5"
_TEXT_DIM = "#a1a1aa"
_TEXT_MUTED = "#71717a"
_DANGER = "#f87171"
_SUCCESS = "#4ade80"

_PHASE_ORDER = ("countdown", "waiting_net", "preparing", "speaking")


# 5x7 bitmap font for the LED-style ticker shown during waiting / preparing.
# Each row is encoded as a 5-bit integer with the leftmost pixel in bit 4.
# Only the characters needed for current ticker messages are encoded —
# extend if you add new strings.
_FONT_5X7: dict[str, list[int]] = {
    "A": [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "B": [0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110],
    "C": [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
    "D": [0b11110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b11110],
    "E": [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111],
    "F": [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000],
    "G": [0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110],
    "H": [0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "I": [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    "K": [0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001],
    "L": [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
    "M": [0b10001, 0b11011, 0b10101, 0b10001, 0b10001, 0b10001, 0b10001],
    "N": [0b10001, 0b11001, 0b10101, 0b10101, 0b10011, 0b10001, 0b10001],
    "O": [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "P": [0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000],
    "R": [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
    "S": [0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110],
    "T": [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    "U": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "V": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
    "W": [0b10001, 0b10001, 0b10001, 0b10001, 0b10101, 0b11011, 0b10001],
    "Y": [0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100],
    " ": [0, 0, 0, 0, 0, 0, 0],
    ".": [0, 0, 0, 0, 0, 0, 0b00100],
    "•": [0, 0, 0, 0b00100, 0b01110, 0b00100, 0],
}


def _hex_to_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#%02x%02x%02x" % (max(0, min(r, 255)), max(0, min(g, 255)), max(0, min(b, 255)))


def _lerp_color(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))


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
    win_h = int(cfg.get("overlay_window_height", 240))
    win_h = max(220, min(win_h, 800))
    # Footer is fixed: this is the author credit, not a per-user setting.
    footer_text = "Built by Rudraksh"

    return {
        "canvas_w": circle_d,
        "win_w": win_w,
        "win_h": win_h,
        "text_cols": text_cols,
        "text_lines": text_lines,
        "code_font_size": code_font_size,
        "wave_h": wave_h,
        "footer_text": footer_text,
    }


def _overlay_main(
    cmd_queue: multiprocessing.Queue,
    feedback_queue: multiprocessing.Queue,
    geom: dict | None = None,
) -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    geom = geom or {}
    win_w = int(geom.get("win_w", 460))
    win_h = int(geom.get("win_h", 268))
    circle_d = int(geom.get("canvas_w", 64))
    text_cols = int(geom.get("text_cols", 48))
    text_lines = int(geom.get("text_lines", 4))
    code_font_size = int(geom.get("code_font_size", 9))

    root = tk.Tk()
    root.title("Victus")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    # Start invisible; fade in once layout is computed for a polished entrance.
    try:
        root.attributes("-alpha", 0.0)
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
    root.configure(bg=_BG_OUTER)

    # Card: thin border + accent strip at top to give the panel identity.
    card = tk.Frame(
        root,
        bg=_BG_CARD,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_BORDER,
    )
    card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    # Animated gradient strip across the top of the card. Three colour stops
    # (purple → magenta → cyan) shift slowly so the card feels alive even when
    # the briefing is idle.
    _strip_h = 4
    accent_strip = tk.Canvas(
        card, bg=_BG_CARD, height=_strip_h, highlightthickness=0, borderwidth=0
    )
    accent_strip.pack(fill=tk.X, side=tk.TOP)
    _strip_state: dict[str, Any] = {"phase": 0.0, "after_id": None, "w": win_w}

    def _draw_gradient_strip() -> None:
        accent_strip.delete("all")
        w = max(1, accent_strip.winfo_width() or _strip_state["w"])
        ph = _strip_state["phase"]
        stops = (_ACCENT, _ACCENT_PINK, _ACCENT_CYAN, _ACCENT)
        n = len(stops) - 1
        # Pre-compute gradient pixels in 2-pixel steps for smooth-but-cheap drawing.
        step = 2
        for x in range(0, w, step):
            t = ((x / max(w - 1, 1)) + ph) % 1.0
            seg = min(int(t * n), n - 1)
            local_t = t * n - seg
            color = _lerp_color(stops[seg], stops[seg + 1], local_t)
            accent_strip.create_rectangle(x, 0, x + step, _strip_h, fill=color, outline="")

    def _animate_strip() -> None:
        _strip_state["phase"] = (_strip_state["phase"] + 0.0035) % 1.0
        _draw_gradient_strip()
        _strip_state["after_id"] = root.after(70, _animate_strip)

    outer = tk.Frame(card, bg=_BG_CARD, padx=16, pady=14)
    outer.pack(fill=tk.BOTH, expand=True)

    title_font = tkfont.Font(family="Segoe UI Semibold", size=10)
    big_font = tkfont.Font(family="Segoe UI", size=32, weight="normal")
    sub_font = tkfont.Font(family="Segoe UI", size=10)
    btn_font = tkfont.Font(family="Segoe UI Semibold", size=9)

    # ---- Title row: status dot + label + phase indicator + close × ----------
    title_row = tk.Frame(outer, bg=_BG_CARD)
    title_row.pack(fill=tk.X)

    # Status dot: a pulsing ring (rendered for cyan/success states) wraps a
    # solid centre dot. Both share one Canvas so the pulse is GPU-cheap.
    _DOT_BOX = 18
    dot = tk.Canvas(
        title_row, width=_DOT_BOX, height=_DOT_BOX, bg=_BG_CARD, highlightthickness=0
    )
    dot.pack(side=tk.LEFT, padx=(0, 8), pady=(2, 0))
    _dot_state: dict[str, Any] = {"color": _ACCENT, "phase": 0.0}

    def _redraw_dot() -> None:
        dot.delete("all")
        c = _dot_state["color"]
        cx = cy = _DOT_BOX / 2.0
        animate = c in (_ACCENT_CYAN, _SUCCESS)
        if animate:
            # Outer halo: expanding ring that fades each cycle.
            k = (math.sin(_dot_state["phase"]) + 1.0) * 0.5  # 0..1
            ring_r = 4.6 + 3.2 * k
            # Tint the halo with the dot colour, blended toward the card bg
            # to fake transparency.
            halo = _lerp_color(_BG_CARD, c, max(0.18, 0.55 - 0.4 * k))
            dot.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, outline=halo, width=1)
            r_inner = 4.0 + 0.6 * k
        else:
            r_inner = 4.5
        dot.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, fill=c, outline="")

    def _animate_dot() -> None:
        _dot_state["phase"] += 0.15
        if _dot_state["color"] in (_ACCENT_CYAN, _SUCCESS):
            _redraw_dot()
        # Active phase dot also breathes — same clock so animations stay in sync.
        try:
            _draw_phase_dots()
        except tk.TclError:
            pass
        root.after(60, _animate_dot)

    title_lbl = tk.Label(
        title_row,
        text="Victus",
        fg=_TEXT,
        bg=_BG_CARD,
        font=title_font,
        anchor="w",
    )
    title_lbl.pack(side=tk.LEFT)

    def on_close_speaking() -> None:
        try:
            feedback_queue.put_nowait({"cmd": "stop_speaking"})
        except Exception:
            pass
        try:
            close_spk_btn.config(state=tk.DISABLED, fg=_TEXT_MUTED)
        except tk.TclError:
            pass

    close_spk_btn = tk.Button(
        title_row,
        text="✕",
        font=title_font,
        fg=_TEXT_DIM,
        bg=_BG_CARD,
        activebackground=_BG_CARD_INNER,
        activeforeground=_DANGER,
        borderwidth=0,
        highlightthickness=0,
        relief=tk.FLAT,
        cursor="hand2",
        padx=6,
        pady=0,
        command=on_close_speaking,
    )

    def _on_close_hover_enter(_e: object) -> None:
        try:
            close_spk_btn.config(fg=_DANGER)
        except tk.TclError:
            pass

    def _on_close_hover_leave(_e: object) -> None:
        try:
            close_spk_btn.config(fg=_TEXT_DIM)
        except tk.TclError:
            pass

    close_spk_btn.bind("<Enter>", _on_close_hover_enter)
    close_spk_btn.bind("<Leave>", _on_close_hover_leave)

    # Phase progress dots: 4 small circles in the title row that show how far
    # the briefing has advanced (countdown → connecting → preparing → speaking).
    _PHASE_DOT_COUNT = 4
    _PHASE_DOT_GAP = 12
    _PHASE_DOT_W = (_PHASE_DOT_COUNT - 1) * _PHASE_DOT_GAP + 12
    phase_canvas = tk.Canvas(
        title_row,
        width=_PHASE_DOT_W,
        height=_DOT_BOX,
        bg=_BG_CARD,
        highlightthickness=0,
    )
    phase_canvas.pack(side=tk.RIGHT, padx=(8, 8))

    def _draw_phase_dots() -> None:
        phase_canvas.delete("all")
        ph = state.get("phase", "countdown")
        if ph == "done":
            cur = _PHASE_DOT_COUNT  # all complete
            done_color = _SUCCESS
            active_color = _SUCCESS
        elif ph == "error":
            cur = -1
            done_color = _DANGER
            active_color = _DANGER
        elif ph in _PHASE_ORDER:
            cur = _PHASE_ORDER.index(ph)
            done_color = _SUCCESS
            active_color = _ACCENT_CYAN if ph in ("waiting_net", "preparing") else _ACCENT
            if ph == "speaking":
                active_color = _SUCCESS
        else:
            cur = 0
            done_color = _SUCCESS
            active_color = _ACCENT
        cy = _DOT_BOX / 2.0
        for i in range(_PHASE_DOT_COUNT):
            cx = 6 + i * _PHASE_DOT_GAP
            if i < cur:
                # completed
                phase_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=done_color, outline="")
            elif i == cur:
                # active — slightly bigger + halo
                k = (math.sin(_dot_state["phase"]) + 1.0) * 0.5
                halo_r = 5.5 + 1.0 * k
                halo = _lerp_color(_BG_CARD, active_color, 0.35)
                phase_canvas.create_oval(cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r, outline=halo, width=1)
                phase_canvas.create_oval(cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5, fill=active_color, outline="")
            else:
                phase_canvas.create_oval(cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5, fill="#3a3a44", outline="")

    footer_font = tkfont.Font(family="Segoe UI", size=8)
    footer_text = str(geom.get("footer_text", "Built by Rudraksh"))
    footer_lbl = tk.Label(outer, text=footer_text, fg=_TEXT_MUTED, bg=_BG_CARD, font=footer_font, anchor="e")
    # Pack footer first at the bottom so body's expand=True can't push it off-screen.
    footer_lbl.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

    body = tk.Frame(outer, bg=_BG_CARD)
    body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    speaking_split = tk.Frame(body, bg=_BG_CARD)

    # ---- Countdown: circular progress ring around the number ------------------
    ring_size = 96
    ring_canvas = tk.Canvas(body, width=ring_size, height=ring_size, bg=_BG_CARD, highlightthickness=0)
    sub_lbl = tk.Label(body, text="Starting briefing", fg=_TEXT_DIM, bg=_BG_CARD, font=sub_font)

    def _draw_countdown_ring(remaining: int, total: int) -> None:
        ring_canvas.delete("all")
        cx = cy = ring_size / 2.0
        r = ring_size / 2.0 - 8
        # Outer halo: a wider, darker arc behind the main ring fakes a glow.
        halo_r = r + 5
        halo = _lerp_color(_BG_CARD, _ACCENT, 0.22)
        ring_canvas.create_oval(cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r, outline=halo, width=2)
        # Track
        ring_canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=_BORDER, width=5)
        # Progress arc (counter-clockwise from top), with a brighter cap dot
        # at the leading edge for a bit of motion / liveliness.
        if total > 0:
            frac = max(0.0, min(1.0, remaining / float(total)))
            extent = -360.0 * frac
            if abs(extent) > 0.1:
                ring_canvas.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    start=90, extent=extent,
                    style=tk.ARC, outline=_ACCENT, width=5,
                )
                # Leading cap: small bright disc at the end of the arc.
                tip_angle_deg = 90.0 + extent
                tip_rad = math.radians(tip_angle_deg)
                tx = cx + r * math.cos(tip_rad)
                ty = cy - r * math.sin(tip_rad)
                ring_canvas.create_oval(tx - 4, ty - 4, tx + 4, ty + 4, fill=_ACCENT_PINK, outline="")
        # Number in the centre. (Smaller ring; "seconds" subtitle dropped.)
        ring_canvas.create_text(
            cx, cy,
            text=str(max(0, int(remaining))),
            fill=_TEXT, font=big_font,
        )

    # ---- Stop button: pill with hover ----------------------------------------
    def on_stop_briefing() -> None:
        try:
            feedback_queue.put_nowait({"cmd": "cancel"})
        except Exception:
            pass
        try:
            stop_btn.config(state=tk.DISABLED, bg=_BG_CARD_INNER, fg=_TEXT_MUTED)
            sub_lbl.config(text="Stopping…", fg=_DANGER)
        except tk.TclError:
            pass

    stop_btn = tk.Button(
        body,
        text="Stop",
        command=on_stop_briefing,
        fg=_TEXT,
        bg="#3f3f46",
        activebackground="#52525b",
        activeforeground=_TEXT,
        font=btn_font,
        padx=18,
        pady=6,
        cursor="hand2",
        relief=tk.FLAT,
        highlightthickness=0,
        borderwidth=0,
    )

    def _on_stop_hover_enter(_e: object) -> None:
        try:
            if stop_btn["state"] != tk.DISABLED:
                stop_btn.config(bg="#52525b")
        except tk.TclError:
            pass

    def _on_stop_hover_leave(_e: object) -> None:
        try:
            if stop_btn["state"] != tk.DISABLED:
                stop_btn.config(bg="#3f3f46")
        except tk.TclError:
            pass

    stop_btn.bind("<Enter>", _on_stop_hover_enter)
    stop_btn.bind("<Leave>", _on_stop_hover_leave)

    # ---- Speaking: transcript (left) + circular waveform (right) -------------
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
        padx=8,
        pady=6,
        highlightthickness=1,
        highlightbackground=_BORDER,
        highlightcolor=_BORDER,
        borderwidth=0,
        cursor="",
        takefocus=0,
        insertbackground="#7dd3fc",
    )
    text_w.tag_configure("dim", foreground="#7dd3fc", font=code_font)
    text_w.tag_configure("hi", foreground="#4ade80", font=code_font_b)
    text_w.tag_configure("cursor", foreground="#22d3ee", font=code_font_b)
    text_w.tag_configure("err", foreground=_DANGER, font=code_font)

    # Right: square frame containing a circular speaking graphic (see draw_siri_waveform)
    wave_wrap = tk.Frame(speaking_split, width=circle_d, height=circle_d, bg=_BG_CARD)
    wave_wrap.pack_propagate(False)
    canvas = tk.Canvas(wave_wrap, width=circle_d, height=circle_d, bg=_BG_CARD, highlightthickness=0)
    canvas.pack(anchor="center")
    cw = circle_d

    # ---- LED-matrix style scrolling ticker (waiting / preparing) -------------
    # A dark panel that renders text as 5x7 lit/dim dots and scrolls
    # right-to-left. Pre-creates one rectangle per pixel and only updates the
    # fill colour each frame so animation stays cheap.
    _TICK_DOT = 10
    _TICK_GAP = 4
    _TICK_CELL = _TICK_DOT + _TICK_GAP  # 14 px per column / row
    _TICK_ROWS = 7
    _TICK_PAD = 10
    _tick_width = max(320, min(win_w - 40, 480))
    _tick_cols = max(1, (_tick_width - _TICK_PAD * 2) // _TICK_CELL)
    _tick_height = _TICK_ROWS * _TICK_CELL + _TICK_PAD * 2
    _TICK_BG = "#08090d"
    _TICK_DIM = "#152a30"

    ticker_frame = tk.Frame(
        body, bg=_BG_CARD,
        highlightthickness=1, highlightbackground=_BORDER, highlightcolor=_BORDER,
    )
    ticker_canvas = tk.Canvas(
        ticker_frame, width=_tick_width, height=_tick_height,
        bg=_TICK_BG, highlightthickness=0, borderwidth=0,
    )
    ticker_canvas.pack()

    _tick_state: dict[str, Any] = {
        "rects": [],
        "text_cols": [],
        "scroll": 0,
    }

    # Pre-create the dot grid once and reuse the rectangles.
    for _x in range(_tick_cols):
        col_rects: list[int] = []
        for _y in range(_TICK_ROWS):
            px = _TICK_PAD + _x * _TICK_CELL
            py = _TICK_PAD + _y * _TICK_CELL
            rect_id = ticker_canvas.create_rectangle(
                px, py, px + _TICK_DOT, py + _TICK_DOT,
                fill=_TICK_DIM, outline="",
            )
            col_rects.append(rect_id)
        _tick_state["rects"].append(col_rects)

    def _ticker_set(text: str) -> None:
        cols: list[int] = []
        # Lead with one screen of empty columns so the message enters from the
        # right edge instead of starting half-drawn.
        cols.extend([0] * _tick_cols)
        for ch in text.upper():
            glyph = _FONT_5X7.get(ch, _FONT_5X7[" "])
            for col_idx in range(5):
                col_bits = 0
                for row_idx in range(_TICK_ROWS):
                    if glyph[row_idx] & (1 << (4 - col_idx)):
                        col_bits |= (1 << row_idx)
                cols.append(col_bits)
            cols.append(0)  # 1-col spacer between glyphs
        # Trailing pad so it scrolls fully off before looping.
        cols.extend([0] * _tick_cols)
        _tick_state["text_cols"] = cols
        _tick_state["scroll"] = 0
        _ticker_render()

    def _ticker_render() -> None:
        cols = _tick_state["text_cols"]
        if not cols:
            return
        n = len(cols)
        s = _tick_state["scroll"]
        rects = _tick_state["rects"]
        for x in range(_tick_cols):
            col_bits = cols[(s + x) % n]
            for y in range(_TICK_ROWS):
                lit = (col_bits >> y) & 1
                color = _ACCENT_CYAN if lit else _TICK_DIM
                try:
                    ticker_canvas.itemconfig(rects[x][y], fill=color)
                except tk.TclError:
                    return

    def _animate_ticker() -> None:
        ph = state.get("phase") if "state" in dir() else None
        # `state` is defined just below; use try/except to skip until ready.
        try:
            ph = state.get("phase")
        except NameError:
            ph = None
        if ph in ("waiting_net", "preparing") and _tick_state["text_cols"]:
            n = len(_tick_state["text_cols"])
            _tick_state["scroll"] = (_tick_state["scroll"] + 1) % n
            try:
                _ticker_render()
            except tk.TclError:
                pass
        root.after(45, _animate_ticker)

    # ---- Done: animated green check ------------------------------------------
    done_canvas = tk.Canvas(body, width=64, height=64, bg=_BG_CARD, highlightthickness=0)

    def _draw_done() -> None:
        done_canvas.delete("all")
        cx = cy = 32
        r = 26
        done_canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#0e2316", outline=_SUCCESS, width=2)
        done_canvas.create_line(cx - 10, cy + 1, cx - 2, cy + 9, fill=_SUCCESS, width=3, capstyle=tk.ROUND)
        done_canvas.create_line(cx - 2, cy + 9, cx + 12, cy - 8, fill=_SUCCESS, width=3, capstyle=tk.ROUND)

    # ---- Error: warning header ------------------------------------------------
    err_header = tk.Frame(outer, bg=_BG_CARD)
    err_icon = tk.Canvas(err_header, width=18, height=18, bg=_BG_CARD, highlightthickness=0)
    err_icon.create_oval(1, 1, 17, 17, fill="#3a0f10", outline=_DANGER, width=1)
    err_icon.create_text(9, 9, text="!", fill=_DANGER, font=tkfont.Font(family="Segoe UI Semibold", size=10))
    err_label = tk.Label(err_header, text="Something went wrong", fg=_DANGER, bg=_BG_CARD, font=title_font, anchor="w")

    state: dict[str, Any] = {
        "phase": "countdown",
        "remaining": 25,
        "countdown_total": 25,
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
        ring_canvas.pack_forget()
        sub_lbl.pack_forget()
        stop_btn.pack_forget()
        canvas.pack_forget()
        wave_wrap.pack_forget()
        text_w.pack_forget()
        try:
            text_w.delete("1.0", tk.END)
        except tk.TclError:
            pass
        speaking_split.pack_forget()
        done_canvas.pack_forget()
        err_header.pack_forget()
        err_icon.pack_forget()
        err_label.pack_forget()
        ticker_frame.pack_forget()
        try:
            close_spk_btn.pack_forget()
            close_spk_btn.config(state=tk.NORMAL, fg=_TEXT_DIM)
        except tk.TclError:
            pass
        try:
            title_lbl.config(text="Victus")
            title_lbl.pack_forget()
            title_lbl.pack(side=tk.LEFT)
        except tk.TclError:
            pass

    def _set_dot(color: str) -> None:
        _dot_state["color"] = color
        _dot_state["phase"] = 0.0
        _redraw_dot()
        try:
            _draw_phase_dots()
        except tk.TclError:
            pass

    # Cycling "•••" indicator for connecting / preparing — a tiny touch that
    # signals the app is alive without committing to a full spinner widget.
    _activity_state: dict[str, Any] = {"base": "", "phase": 0}

    def _animate_activity() -> None:
        ph = state.get("phase")
        if ph in ("waiting_net", "preparing") and _activity_state["base"]:
            _activity_state["phase"] = (_activity_state["phase"] + 1) % 4
            n = _activity_state["phase"]
            dots = "•" * n + " " * (3 - n)
            try:
                sub_lbl.config(text=f"{_activity_state['base']}  {dots}")
            except tk.TclError:
                pass
        root.after(280, _animate_activity)

    def show_countdown(n: int) -> None:
        clear_body()
        state["phase"] = "countdown"
        _activity_state["base"] = ""
        state["remaining"] = max(0, int(n))
        # First tick locks in the total so the ring animates correctly.
        if state["countdown_total"] < state["remaining"]:
            state["countdown_total"] = state["remaining"]
        if state["countdown_total"] <= 0:
            state["countdown_total"] = max(1, state["remaining"])
        _set_dot(_ACCENT)
        title_lbl.config(text="Starting briefing")
        sub_lbl.config(text="Briefing begins in a moment", fg=_TEXT_DIM)
        try:
            stop_btn.config(state=tk.NORMAL, bg="#3f3f46", fg=_TEXT)
        except tk.TclError:
            pass
        _draw_countdown_ring(state["remaining"], state["countdown_total"])
        ring_canvas.pack(pady=(2, 4))
        sub_lbl.pack()
        stop_btn.pack(pady=(10, 0))

    def show_waiting_net() -> None:
        clear_body()
        state["phase"] = "waiting_net"
        _set_dot(_ACCENT_CYAN)
        title_lbl.config(text="Connecting")
        _activity_state["base"] = ""  # ticker carries the message now
        _ticker_set("WAITING FOR THE NETWORK   •••")
        try:
            stop_btn.config(state=tk.NORMAL, bg="#3f3f46", fg=_TEXT)
        except tk.TclError:
            pass
        ticker_frame.pack(pady=(8, 2))
        stop_btn.pack(pady=(8, 0))

    def show_preparing() -> None:
        clear_body()
        state["phase"] = "preparing"
        _set_dot(_ACCENT_CYAN)
        title_lbl.config(text="Preparing")
        _activity_state["base"] = ""
        _ticker_set("RENDERING AUDIO   •••")
        try:
            stop_btn.config(state=tk.NORMAL, bg="#3f3f46", fg=_TEXT)
        except tk.TclError:
            pass
        ticker_frame.pack(pady=(8, 2))
        stop_btn.pack(pady=(8, 0))

    def show_error(err_text: str) -> None:
        """Same Text widget as the transcript; waveform hidden; close × becomes dismiss."""
        if state.get("after_id"):
            try:
                root.after_cancel(state["after_id"])
            except Exception:
                pass
            state["after_id"] = None
        clear_body()
        state["phase"] = "error"
        _set_dot(_DANGER)
        title_lbl.config(text="Victus")
        err_header.pack(fill=tk.X, pady=(0, 6))
        err_icon.pack(side=tk.LEFT, padx=(0, 8))
        err_label.pack(side=tk.LEFT)
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
        # Cursor only while still typing — once the line is fully written we
        # leave it clean so a trailing block glyph can't be misread as a stray
        # letter when the briefing closes.
        if tc < len(target):
            blink = (int(state.get("anim_t", 0) * 12) % 2) == 0
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
        _set_dot(_SUCCESS)
        title_lbl.config(text="Voice assistant")
        sub_lbl.config(text="", fg=_TEXT_DIM)
        speaking_split.pack(fill=tk.BOTH, expand=True)
        text_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        wave_wrap.pack(side=tk.RIGHT, anchor=tk.CENTER)
        canvas.pack(anchor="center")
        try:
            close_spk_btn.pack(side=tk.RIGHT, anchor="ne")
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
        _set_dot(_SUCCESS)
        title_lbl.config(text="Briefing complete")
        _draw_done()
        done_canvas.pack(pady=(20, 6))
        sub_lbl.config(text="Have a great day", fg=_TEXT_DIM)
        sub_lbl.pack()

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

    _redraw_dot()
    _animate_dot()
    show_countdown(25)
    root.update_idletasks()
    _strip_state["w"] = max(_strip_state["w"], accent_strip.winfo_width())
    _draw_gradient_strip()
    _animate_strip()
    _animate_activity()
    _animate_ticker()

    # Fade window in over ~280ms — alpha 0 → 0.96 in 14 ticks of 20ms each.
    def _fade_in(step: int = 0) -> None:
        target = 0.96
        steps = 14
        if step >= steps:
            try:
                root.attributes("-alpha", target)
            except tk.TclError:
                pass
            return
        try:
            # Ease-out: faster early, smoother near the end.
            t = step / float(steps)
            ease = 1.0 - (1.0 - t) ** 2
            root.attributes("-alpha", target * ease)
        except tk.TclError:
            pass
        root.after(20, lambda: _fade_in(step + 1))

    root.after(40, _fade_in)
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
        self._spawn_wait = cfg_float(cfg, "overlay_child_process_ready_seconds", 0.85, 0.2, 3.0)
        self._proc: Process | None = None
        self._q: multiprocessing.Queue | None = None
        self._feedback_q: multiprocessing.Queue | None = None
        self._pending_cancel = False
        self._pending_stop_speaking = False

    def start(self) -> None:
        if not self._enabled:
            return
        from ..runtime_support import autostart_log

        last_err: BaseException | None = None
        for attempt in range(1, 4):
            try:
                autostart_log(f"overlay starting geom={self._geom} attempt={attempt}")
                ctx = multiprocessing.get_context("spawn")
                self._q = ctx.Queue()
                self._feedback_q = ctx.Queue()
                self._proc = ctx.Process(
                    target=_overlay_main,
                    args=(self._q, self._feedback_q, self._geom),
                    daemon=True,
                )
                self._proc.start()
                time.sleep(self._spawn_wait)
                return
            except Exception as e:
                last_err = e
                autostart_log(f"overlay spawn attempt {attempt} failed: {e!r}")
                self._q = None
                self._feedback_q = None
                self._proc = None
                time.sleep(1.2 * attempt)
        if last_err is not None:
            raise last_err

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
        time.sleep(1.6)
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
