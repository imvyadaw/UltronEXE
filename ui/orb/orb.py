"""
Voice orb UI
============
A futuristic HUD-style floating window - not a status circle with
a caption, but a proper heads-up display:

  - a hexagonal reactor core with a rotating hex gear ring and an inner
    scanline that sweeps the "screen" like a radar display
  - two counter-rotating segmented rangefinder rings (clustered blade
    ticks, not a smooth circle - like a camera iris / lens aperture)
  - a targeting crosshair through the core
  - a radial spectrum ring of 64 bars around the outside that bounce
    with Ultron's state instead of a flat waveform strip
  - four corner telemetry readouts (bearing / hex id / power / freq)
    that tick over on their own, purely cosmetic - the "busy" detail
    real HUD mockups have
  - chamfered (cut-corner) panels for the header and stat tiles instead
    of plain rectangles
  - a slow scanline sweep over the whole panel for a CRT feel
  - a side telemetry console that logs the actual conversation
    ("You: ..." / "ULTRON: ...") as it happens

Colors and animation speed shift with Ultron's live state (idle /
listening / thinking / speaking / tool / error). Off by default - opened
either by starting Ultron with --ui, or at runtime via the voice command
"UI mode on" (see ai/local_router.py + main.py), and closed again with
"UI mode off".

Built on the same TkWindow helper as ui/dashboard and ui/overlay (its own
background thread + thread-safe post() queue), so it never touches
main.py's blocking input()/listen loop and is safe to open/close whenever.

Requires: tkinter only (no new dependency). Never raises on a machine
without a display backend - callers should treat open_orb()/close_orb()
as best-effort, same as the rest of ui/.
"""

import math
import time
from typing import Optional

from core.events import get_event_bus
from core.logger import get_logger
from ui.widgets.widgets import TkWindow, BG, FG, FG_DIM

logger = get_logger("ultron.ui.orb")

# HUD palette: (core color, glow color, ring color) per state.
STATE_PALETTE = {
    "idle": ("#2fb9d8", "#0c2a33", "#1c4550"),
    "listening": ("#37e6ff", "#0a3540", "#1fa9c2"),
    "thinking": ("#ffb02e", "#3a2405", "#d68c1a"),
    "speaking": ("#4ade80", "#0f3324", "#2fae63"),
    "tool": ("#37e6ff", "#0a3540", "#1fa9c2"),
    "error": ("#ff4d4d", "#3d0f0f", "#c23636"),
}

STATE_LABELS = {
    "idle": "SYSTEMS ONLINE",
    "listening": "LISTENING",
    "thinking": "PROCESSING",
    "speaking": "SPEAKING",
    "tool": "EXECUTING",
    "error": "ERROR",
}

_window: Optional[TkWindow] = None
_wired = False

# Reactor canvas geometry - everything below is relative to these so the
# whole HUD scales cleanly if CANVAS_W/H ever change.
CANVAS_W, CANVAS_H = 480, 480
CX, CY = 240, 240
N_SPECTRUM = 64
AMBER = "#ffb02e"


def _spaced(text: str) -> str:
    """'SYSTEMS ONLINE' -> 'S Y S T E M S   O N L I N E' - cheap letter
    tracking so tkinter labels read like a HUD readout instead of a
    normal UI label. Spaces in the source become a wider gap."""
    return "".join(ch + " " if ch != " " else "  " for ch in text).rstrip()


def _lerp_color(c1: str, c2: str, t: float) -> str:
    c1 = c1.lstrip("#")
    c2 = c2.lstrip("#")
    r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
    r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
    t = max(0.0, min(1.0, t))
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _chamfer(x1, y1, x2, y2, c):
    """Point list for a rectangle with its corners cut at 45 degrees
    (the "sci-fi panel" look), for canvas.create_polygon."""
    return [
        x1 + c,
        y1,
        x2 - c,
        y1,
        x2,
        y1 + c,
        x2,
        y2 - c,
        x2 - c,
        y2,
        x1 + c,
        y2,
        x1,
        y2 - c,
        x1,
        y1 + c,
    ]


def _hex_points(cx, cy, r, rot_deg=0.0):
    pts = []
    for i in range(6):
        a = math.radians(60 * i + rot_deg)
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def _build(win: TkWindow, root):
    import tkinter as tk

    root.overrideredirect(False)
    try:
        root.attributes("-alpha", 0.98)
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.orb.orb._build")
    root.configure(bg=BG)
    root.resizable(False, False)

    outer = tk.Frame(root, bg="#1c4550", padx=1, pady=1)
    outer.pack(fill="both", expand=True)
    body = tk.Frame(outer, bg=BG)
    body.pack(fill="both", expand=True)

    # Small chamfer accent marks at the four corners of the whole panel.
    for corner in ("nw", "ne", "sw", "se"):
        c = tk.Canvas(root, width=22, height=22, bg=BG, highlightthickness=0)
        pts = {
            "nw": (2, 20, 2, 2, 20, 2),
            "ne": (0, 2, 20, 2, 20, 20),
            "sw": (2, 0, 2, 20, 20, 20),
            "se": (0, 20, 20, 20, 20, 0),
        }[corner]
        c.create_line(*pts, fill="#37e6ff", width=2)
        anchor = {"nw": "nw", "ne": "ne", "sw": "sw", "se": "se"}[corner]
        relx = {"nw": 0.0, "ne": 1.0, "sw": 0.0, "se": 1.0}[corner]
        rely = {"nw": 0.0, "ne": 0.0, "sw": 1.0, "se": 1.0}[corner]
        c.place(relx=relx, rely=rely, anchor=anchor, x=(2 if "w" in corner else -2), y=(2 if "n" in corner else -2))

    # ---- header: chamfered tab panel instead of a plain label --------
    header_canvas = tk.Canvas(body, height=68, bg=BG, highlightthickness=0)
    header_canvas.pack(fill="x", padx=16, pady=(14, 0))
    win.header_canvas = header_canvas

    def _draw_header(event=None):
        header_canvas.delete("panel")
        w = header_canvas.winfo_width() or 760
        pts = _chamfer(0, 0, w, 66, 16)
        header_canvas.create_polygon(pts, fill="#0a0e14", outline="#1c4550", width=1, tags="panel")
        header_canvas.create_line(0, 66, w, 66, fill="#37e6ff", width=1, tags="panel")
        header_canvas.tag_lower("panel")

    header_canvas.bind("<Configure>", _draw_header)
    win.title_text = header_canvas.create_text(
        0, 24, text=_spaced("J.A.R.V.I.S."), fill="#37e6ff", font=("Consolas", 20, "bold"), tags="fg"
    )
    win.status_text = header_canvas.create_text(
        0, 50, text=_spaced(STATE_LABELS["idle"]), fill="#c9d1d9", font=("Consolas", 10, "bold"), tags="fg"
    )

    def _center_header(event=None):
        w = header_canvas.winfo_width() or 760
        header_canvas.coords(win.title_text, w / 2, 24)
        header_canvas.coords(win.status_text, w / 2, 50)

    header_canvas.bind("<Configure>", lambda e: (_draw_header(e), _center_header(e)))

    # ---- main split: reactor canvas (left) + telemetry console (right)
    main = tk.Frame(body, bg=BG)
    main.pack(fill="both", expand=True, padx=12, pady=12)

    canvas = tk.Canvas(main, width=CANVAS_W, height=CANVAS_H, bg=BG, highlightthickness=0)
    canvas.pack(side="left", fill="y")
    win.canvas = canvas

    right = tk.Frame(main, bg=BG, width=280)
    right.pack(side="left", fill="both", expand=True, padx=(16, 0))
    right.pack_propagate(False)

    # ---- telemetry stat tiles: chamfered mini-panels with a gauge bar
    stats_canvas = tk.Canvas(right, height=78, bg=BG, highlightthickness=0)
    stats_canvas.pack(fill="x")
    win.stats_canvas = stats_canvas
    win.stat_defs = [
        {"label": "MODE", "value": "GROQ", "gauge": None},
        {"label": "UPTIME", "value": "00:00", "gauge": None},
        {"label": "TOOL CALLS", "value": "0", "gauge": 0.0},
    ]
    win.tool_count = 0

    def _draw_stats(event=None):
        stats_canvas.delete("all")
        w = stats_canvas.winfo_width() or 280
        gap = 8
        tile_w = (w - gap * 2) / 3
        win.stat_items = []
        for i, d in enumerate(win.stat_defs):
            x1 = i * (tile_w + gap)
            x2 = x1 + tile_w
            stats_canvas.create_polygon(_chamfer(x1, 0, x2, 78, 8), fill="#0a0e14", outline="#1c4550")
            stats_canvas.create_text(x1 + 8, 16, text=d["label"], fill=FG_DIM, font=("Consolas", 7, "bold"), anchor="w")
            val_id = stats_canvas.create_text(
                x1 + 8, 38, text=d["value"], fill=FG, font=("Consolas", 13, "bold"), anchor="w"
            )
            bar_bg = stats_canvas.create_rectangle(x1 + 8, 60, x2 - 8, 65, fill="#111820", outline="")
            bar_fg = stats_canvas.create_rectangle(x1 + 8, 60, x1 + 8, 65, fill="#1fa9c2", outline="")
            win.stat_items.append({"val": val_id, "bar_bg": bar_bg, "bar_fg": bar_fg, "x1": x1 + 8, "x2": x2 - 8})

    stats_canvas.bind("<Configure>", _draw_stats)

    tk.Label(right, text=_spaced("LIVE CONSOLE"), bg=BG, fg="#5c6773", font=("Consolas", 9, "bold")).pack(
        anchor="w", pady=(12, 4)
    )

    console_frame = tk.Frame(right, bg="#1c4550")
    console_frame.pack(fill="both", expand=True)
    inner_console = tk.Frame(console_frame, bg="#0a0e14")
    inner_console.pack(fill="both", expand=True, padx=1, pady=1)
    win.console = tk.Text(
        inner_console,
        bg="#0a0e14",
        fg=FG,
        insertbackground=FG,
        font=("Consolas", 9),
        wrap="word",
        state="disabled",
        relief="flat",
        padx=8,
        pady=6,
    )
    scrollbar = tk.Scrollbar(inner_console, command=win.console.yview)
    win.console.configure(yscrollcommand=scrollbar.set)
    win.console.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    win.console.tag_config("you", foreground="#58a6ff")
    win.console.tag_config("ultron", foreground="#4ade80")
    win.console.tag_config("tool", foreground=AMBER)
    win.console.tag_config("err", foreground="#f85149")
    win.console.tag_config("dim", foreground=FG_DIM)

    win.state = "idle"
    win.t0 = time.time()
    win.start_time = time.time()

    # ==================================================================
    # Reactor canvas contents
    # ==================================================================

    # Faint static scan-grid dots.
    for gx in range(0, CANVAS_W, 24):
        for gy in range(0, CANVAS_H, 24):
            canvas.create_oval(gx - 1, gy - 1, gx + 1, gy + 1, fill="#0e141b", outline="")

    # Outer ring boundary (very dim, mostly structural).
    canvas.create_oval(CX - 216, CY - 216, CX + 216, CY + 216, outline="#131c24", width=1)

    # -- crosshair reticle (static), gapped near the core -------------
    for x1, y1, x2, y2 in [
        (CX - 205, CY, CX - 70, CY),
        (CX + 70, CY, CX + 205, CY),
        (CX, CY - 205, CX, CY - 70),
        (CX, CY + 70, CX, CY + 205),
    ]:
        canvas.create_line(x1, y1, x2, y2, fill="#16222b", width=1)
    for r in (205,):
        for a in (0, 90, 180, 270):
            rad = math.radians(a)
            x, y = CX + r * math.cos(rad), CY + r * math.sin(rad)
            canvas.create_line(x - 5, y, x + 5, y, fill="#2a3f4a", width=1)
            canvas.create_line(x, y - 5, x, y + 5, fill="#2a3f4a", width=1)

    # -- radial spectrum ring (replaces a flat waveform strip) --------
    win.spectrum_bars = []
    for i in range(N_SPECTRUM):
        win.spectrum_bars.append(canvas.create_line(0, 0, 0, 0, fill="", width=2))

    # -- two counter-rotating segmented rangefinder rings --------------
    win.ring_a = [canvas.create_line(0, 0, 0, 0, fill="", width=3) for _ in range(24)]
    win.ring_b = [canvas.create_line(0, 0, 0, 0, fill="", width=3) for _ in range(18)]

    # -- hex gear ring + hex core screen --------------------------------
    win.hex_glow = canvas.create_polygon(_hex_points(CX, CY, 60), fill=BG, outline="")
    win.hex_outer = canvas.create_polygon(_hex_points(CX, CY, 58), fill="", outline="#1c4550", width=2)
    win.hex_outer2 = canvas.create_polygon(_hex_points(CX, CY, 66, 30), fill="", outline="#1c4550", width=1)
    win.hex_core = canvas.create_polygon(
        _hex_points(CX, CY, 44), fill=STATE_PALETTE["idle"][0], outline="#e8fbff", width=1
    )
    win.hex_scan = canvas.create_line(CX - 38, CY, CX + 38, CY, fill="#e8fbff", width=1)

    # -- corner telemetry readouts (cosmetic, self-updating) ------------
    win.corner_labels = {}
    corner_pos = {
        "tl": (10, 10, "nw"),
        "tr": (CANVAS_W - 10, 10, "ne"),
        "bl": (10, CANVAS_H - 24, "nw"),
        "br": (CANVAS_W - 10, CANVAS_H - 24, "ne"),
    }
    for key, (x, y, anchor) in corner_pos.items():
        line1 = canvas.create_text(x, y, text="", fill="#3a5560", font=("Consolas", 8, "bold"), anchor=anchor)
        line2 = canvas.create_text(x, y + 12, text="", fill="#2a3f4a", font=("Consolas", 8), anchor=anchor)
        win.corner_labels[key] = (line1, line2)

    # -- slow CRT-style scanline sweep -----------------------------------
    win.scanline = canvas.create_line(0, 0, CANVAS_W, 0, fill="#132029", width=2)

    # -- corner HUD brackets ---------------------------------------------
    b = 20
    for x1, y1, x2, y2, x3, y3 in [
        (6, 6 + b, 6, 6, 6 + b, 6),
        (CANVAS_W - b, 6, CANVAS_W, 6, CANVAS_W, 6 + b),
        (6, CANVAS_H - b, 6, CANVAS_H, 6 + b, CANVAS_H),
        (CANVAS_W - b, CANVAS_H, CANVAS_W, CANVAS_H, CANVAS_W, CANVAS_H - b),
    ]:
        canvas.create_line(x1, y1, x2, y2, x3, y3, fill="#1c4550", width=2)

    win.caption_label = tk.Label(
        canvas.master,
        text="",
        bg=BG,
        fg="#5c6773",
        font=("Consolas", 9),
        wraplength=CANVAS_W,
        justify="center",
    )
    win.caption_label.pack(pady=(4, 0))

    root.update_idletasks()
    _draw_header()
    _center_header()
    _draw_stats()

    _animate(win)
    _tick_uptime(win)


def _tick_uptime(win: TkWindow):
    if not win.root:
        return
    try:
        elapsed = int(time.time() - win.start_time)
        win.stat_defs[1]["value"] = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        win.stats_canvas.itemconfig(win.stat_items[1]["val"], text=win.stat_defs[1]["value"])
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.orb.orb._tick_uptime")
    win.root.after(1000, lambda: _tick_uptime(win))


def _console_append(win: TkWindow, text: str, tag: str):
    try:
        win.console.config(state="normal")
        win.console.insert("end", text + "\n", tag)
        line_count = int(win.console.index("end-1c").split(".")[0])
        if line_count > 400:
            win.console.delete("1.0", "2.0")
        win.console.see("end")
        win.console.config(state="disabled")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.orb.orb._console_append")


def _animate(win: TkWindow):
    if not win.root:
        return
    try:
        canvas = win.canvas
        core_color, glow_color, ring_color = STATE_PALETTE.get(win.state, STATE_PALETTE["idle"])
        elapsed = time.time() - win.t0

        speed = {"idle": 0.5, "listening": 1.8, "thinking": 2.6, "speaking": 2.2, "tool": 2.4, "error": 0.9}.get(
            win.state, 1.0
        )
        pulse = (math.sin(elapsed * speed) + 1) / 2  # 0..1
        active = win.state in ("listening", "thinking", "tool", "speaking")

        # -- hex core: breathing scale + color, gear ring counter-rotating
        scale = 1.0 + pulse * 0.12
        canvas.coords(win.hex_core, *_hex_points(CX, CY, 44 * scale))
        canvas.itemconfig(win.hex_core, fill=core_color)
        canvas.coords(win.hex_glow, *_hex_points(CX, CY, 66 * scale))
        canvas.itemconfig(win.hex_glow, fill=_lerp_color(BG, glow_color, 1.0))
        canvas.tag_lower(win.hex_glow)
        canvas.tag_raise(win.hex_glow, win.spectrum_bars[0] if win.spectrum_bars else win.hex_glow)

        rot_speed = {"idle": 8, "listening": 40, "thinking": 70, "speaking": 55, "tool": 60, "error": 15}.get(
            win.state, 15
        )
        gear_ang = (elapsed * rot_speed) % 360
        canvas.coords(win.hex_outer, *_hex_points(CX, CY, 58, gear_ang))
        canvas.coords(win.hex_outer2, *_hex_points(CX, CY, 68, -gear_ang * 0.6 + 30))
        canvas.itemconfig(win.hex_outer, outline=ring_color)
        canvas.itemconfig(win.hex_outer2, outline=core_color)

        # Inner scanline bouncing top/bottom inside the hex like a radar screen.
        scan_t = (math.sin(elapsed * 2.2) + 1) / 2
        scan_y = CY - 30 + scan_t * 60
        half_w = 38 * (0.5 + 0.5 * math.sin(scan_t * math.pi))
        canvas.coords(win.hex_scan, CX - half_w, scan_y, CX + half_w, scan_y)
        canvas.itemconfig(win.hex_scan, fill=_lerp_color(BG, "#ffffff", 0.8))

        # -- rangefinder rings: clustered blade ticks, counter-rotating --
        for ring_ids, radius, n, cluster, gap, dirn in (
            (win.ring_a, 128, len(win.ring_a), 3, 2, 1),
            (win.ring_b, 168, len(win.ring_b), 2, 3, -1),
        ):
            ang0 = dirn * elapsed * (rot_speed * 1.3)
            for i, seg in enumerate(ring_ids):
                a = math.radians((i / n) * 360 + ang0)
                lit = (i % (cluster + gap)) < cluster
                r1, r2 = radius, radius + (16 if lit else 8)
                x1, y1 = CX + r1 * math.cos(a), CY + r1 * math.sin(a)
                x2, y2 = CX + r2 * math.cos(a), CY + r2 * math.sin(a)
                canvas.coords(seg, x1, y1, x2, y2)
                canvas.itemconfig(seg, fill=core_color if lit else _lerp_color(BG, ring_color, 0.4))

        # -- radial spectrum ring around the outside ----------------------
        n = len(win.spectrum_bars)
        for i, bar in enumerate(win.spectrum_bars):
            a = math.radians((i / n) * 360)
            if active:
                amp = 6 + abs(math.sin(elapsed * 5 + i * 0.9)) * (26 if win.state in ("listening", "speaking") else 16)
            else:
                amp = 4 + abs(math.sin(elapsed * 1.1 + i * 0.6)) * 4
            r1 = 192
            r2 = r1 + amp
            x1, y1 = CX + r1 * math.cos(a), CY + r1 * math.sin(a)
            x2, y2 = CX + r2 * math.cos(a), CY + r2 * math.sin(a)
            canvas.coords(bar, x1, y1, x2, y2)
            canvas.itemconfig(bar, fill=_lerp_color(BG, core_color, 0.4 + 0.5 * (amp / 32)))

        # -- CRT scanline sweep, top to bottom, looping --------------------
        sweep_y = (elapsed * 70) % (CANVAS_H + 40) - 20
        canvas.coords(win.scanline, 0, sweep_y, CANVAS_W, sweep_y)
        canvas.itemconfig(win.scanline, fill=_lerp_color(BG, ring_color, 0.5))

        # -- cosmetic corner telemetry, ticks on its own -------------------
        az = (elapsed * 11) % 360
        hexid = int((math.sin(elapsed * 2.3) * 0.5 + 0.5) * 0xFFFF)
        pwr = 92 + 6 * math.sin(elapsed * 0.7)
        freq = 2.40 + 0.05 * math.sin(elapsed * 1.3)
        l1, l2 = win.corner_labels["tl"]
        canvas.itemconfig(l1, text="BEARING", fill=_lerp_color(BG, ring_color, 0.9))
        canvas.itemconfig(l2, text=f"AZ {az:05.1f}°", fill=_lerp_color(BG, core_color, 0.8))
        l1, l2 = win.corner_labels["tr"]
        canvas.itemconfig(l1, text="SIGNAL ID", fill=_lerp_color(BG, ring_color, 0.9))
        canvas.itemconfig(l2, text=f"0x{hexid:04X}", fill=_lerp_color(BG, core_color, 0.8))
        l1, l2 = win.corner_labels["bl"]
        canvas.itemconfig(l1, text="PWR CORE", fill=_lerp_color(BG, ring_color, 0.9))
        canvas.itemconfig(l2, text=f"{pwr:05.1f}%", fill=_lerp_color(BG, core_color, 0.8))
        l1, l2 = win.corner_labels["br"]
        canvas.itemconfig(l1, text="UPLINK", fill=_lerp_color(BG, ring_color, 0.9))
        canvas.itemconfig(l2, text=f"{freq:.2f} GHz", fill=_lerp_color(BG, core_color, 0.8))

        canvas.itemconfig(
            win.status_text, text=_spaced(STATE_LABELS.get(win.state, win.state.upper())), fill=core_color
        )

        # Tool-call gauge bar fills toward a soft cap of 20 calls, just a
        # bit of visual life on the stat tile rather than a real metric.
        try:
            item = win.stat_items[2]
            frac = min(1.0, win.tool_count / 20.0)
            canvas.coords(item["bar_fg"], item["x1"], 60, item["x1"] + (item["x2"] - item["x1"]) * frac, 65)
            canvas.itemconfig(item["bar_fg"], fill=core_color)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.orb.orb._animate")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.orb.orb._animate")

    win.root.after(30, lambda: _animate(win))


def _on_event(win: TkWindow, event: str, data: dict):
    if event == "state":
        win.state = data.get("state", "idle")
        win.t0 = time.time()
        caption = data.get("text")
        if caption:
            win.caption_label.config(text=caption[:200])
        if win.state == "error":
            # Errors don't have a natural "done" event the way
            # thinking/speaking do, so recover on a timer instead -
            # otherwise the reactor would sit red forever after one error.
            win.root.after(6000, lambda: _recover_from_error(win))
    elif event == "log":
        _console_append(win, data.get("text", ""), data.get("tag", "dim"))
    elif event == "mode":
        win.stat_defs[0]["value"] = data.get("mode", "-")
        win.stats_canvas.itemconfig(win.stat_items[0]["val"], text=win.stat_defs[0]["value"])
    elif event == "tool_count":
        win.tool_count += 1
        win.stat_defs[2]["value"] = str(win.tool_count)
        win.stats_canvas.itemconfig(win.stat_items[2]["val"], text=win.stat_defs[2]["value"])


def _recover_from_error(win: TkWindow):
    if win.state == "error":
        win.state = "idle"
        win.t0 = time.time()
        win.caption_label.config(text="")


def _wire_events(win: TkWindow):
    global _wired
    if _wired:
        return
    _wired = True
    bus = get_event_bus()

    def state(name, text=None):
        win.post("state", state=name, text=text)

    def log(text, tag):
        win.post("log", text=text, tag=tag)

    def on_thinking(**kw):
        text = kw.get("text")
        state("thinking", text)
        if text:
            log(f"You: {text}", "you")

    def on_tool(**kw):
        name = kw.get("name")
        args_str = kw.get("args_str", "")
        state("tool", f"{name}({args_str})")
        log(f"[tool] {name}({args_str})", "tool")
        win.post("tool_count")

    def on_response(**kw):
        text = kw.get("text")
        state("idle", text)
        if text:
            log(f"ULTRON: {text}", "ultron")

    def on_error(**kw):
        text = kw.get("text", "") or ""
        state("error", text[:60])
        log(f"[error] {text}", "err")

    def on_mode_switch(**kw):
        win.post("mode", mode=str(kw.get("to_mode", "-")).upper())

    bus.subscribe("thinking_start", on_thinking)
    bus.subscribe("tool_executed", on_tool)
    bus.subscribe("response_ready", on_response)
    bus.subscribe("speaking_start", lambda **kw: state("speaking"))
    bus.subscribe("speaking_end", lambda **kw: state("idle"))
    bus.subscribe("wake_detected", lambda **kw: state("listening"))
    bus.subscribe("error", on_error)
    bus.subscribe("ai_mode_switch", on_mode_switch)


def open_orb() -> Optional[TkWindow]:
    """Open the voice orb window (idempotent - no-ops if already open).
    Never raises; returns None if tkinter isn't available."""
    global _window
    try:
        if _window is None or not _window.is_alive():
            _window = TkWindow("ULTRON", build=_build, on_event=_on_event, size="820x640")
            _window.start()
            _window.wait_ready()
        _wire_events(_window)
        return _window
    except Exception as e:
        logger.warning(f"Voice orb UI unavailable: {e}")
        return None


def close_orb():
    """Close the voice orb window if it's open. Safe to call even if it
    was never opened."""
    global _window
    if _window is not None:
        try:
            _window.close()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.orb.orb.close_orb")
        _window = None


def is_orb_open() -> bool:
    return _window is not None and _window.is_alive()


class Overlay:
    """Kept for import-compatibility - some scaffolding referred to the
    orb window through ui.orb.orb.Overlay()."""

    def show(self, *args, **kwargs):
        return open_orb()
