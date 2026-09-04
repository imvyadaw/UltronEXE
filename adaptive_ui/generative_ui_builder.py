"""
Generative UI builder
========================
Renders a tkinter panel from a small JSON-like spec at runtime, on top
of ui/widgets/widgets.py's TkWindow - for panels whose layout isn't
known ahead of time (e.g. composed by the brain to show "the 3 options
you asked about" or "form fields for the trip you're booking") instead
of every possible panel needing its own hand-written ui/ module.

Deliberately small and safe: a fixed, closed set of widget "types"
(label, button, entry, checkbox, divider, progress) map to plain tkinter
widgets - there is no eval() of arbitrary code or arbitrary Python
callables in the spec. A `button`'s "action" is a plain string id;
resolving that id to real behavior is the caller's job (via `on_action`),
so this module never has to trust or execute code embedded in a spec
that might have come from an LLM.

Spec shape:
    {
      "title": "Book flight",
      "widgets": [
        {"type": "label", "text": "Choose a departure city"},
        {"type": "entry", "id": "from_city", "placeholder": "City"},
        {"type": "checkbox", "id": "roundtrip", "text": "Round trip", "default": true},
        {"type": "divider"},
        {"type": "button", "id": "confirm", "text": "Book it", "action": "confirm_booking"},
      ]
    }
"""

from typing import Callable, Dict, Optional

from ui.widgets.widgets import TkWindow, BG, BG_PANEL, FG, FG_DIM, ACCENT
from core.logger import get_logger

logger = get_logger("ultron.interaction.generative_ui")

_ALLOWED_TYPES = {"label", "button", "entry", "checkbox", "divider", "progress"}


class GeneratedPanel:
    """One rendered panel. Holds the live tkinter widget handles (via the
    underlying TkWindow) and the current form values, readable with
    get_values() once the user has interacted with it."""

    def __init__(self, spec: Dict, on_action: Optional[Callable[[str, Dict], None]] = None):
        self._spec = spec
        self._on_action = on_action or (lambda action_id, values: None)
        self._values: Dict = {}
        self._window: Optional[TkWindow] = None

    def _build(self, win: TkWindow, root):
        import tkinter as tk

        win.entries = {}
        win.checks = {}

        tk.Label(root, text=self._spec.get("title", ""), bg=BG, fg=FG, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=12, pady=(12, 8)
        )

        for w in self._spec.get("widgets", []):
            wtype = w.get("type")
            if wtype not in _ALLOWED_TYPES:
                logger.warning(f"Skipping unknown generative UI widget type: {wtype!r}")
                continue

            if wtype == "label":
                tk.Label(
                    root,
                    text=w.get("text", ""),
                    bg=BG,
                    fg=FG_DIM,
                    font=("Segoe UI", 10),
                    wraplength=360,
                    justify="left",
                ).pack(anchor="w", padx=12, pady=2)

            elif wtype == "divider":
                tk.Frame(root, bg=FG_DIM, height=1).pack(fill="x", padx=12, pady=8)

            elif wtype == "entry":
                var = tk.StringVar(value=w.get("default", ""))
                entry = tk.Entry(root, textvariable=var, bg=BG_PANEL, fg=FG, insertbackground=FG, relief="flat")
                entry.pack(fill="x", padx=12, pady=4)
                if w.get("placeholder") and not w.get("default"):
                    entry.insert(0, w["placeholder"])
                win.entries[w.get("id", w.get("text", ""))] = var

            elif wtype == "checkbox":
                var = tk.BooleanVar(value=bool(w.get("default", False)))
                tk.Checkbutton(
                    root,
                    text=w.get("text", ""),
                    variable=var,
                    bg=BG,
                    fg=FG,
                    selectcolor=BG_PANEL,
                    activebackground=BG,
                    activeforeground=FG,
                ).pack(anchor="w", padx=8, pady=2)
                win.checks[w.get("id", w.get("text", ""))] = var

            elif wtype == "progress":
                pct = max(0, min(100, int(w.get("percent", 0))))
                canvas = tk.Canvas(root, width=360, height=10, bg=BG_PANEL, highlightthickness=0)
                canvas.create_rectangle(0, 0, 360 * pct / 100, 10, fill=ACCENT, outline="")
                canvas.pack(padx=12, pady=6)

            elif wtype == "button":
                action_id = w.get("action", w.get("id", "button"))

                def make_handler(aid=action_id):
                    def handler():
                        values = {k: v.get() for k, v in win.entries.items()}
                        values.update({k: v.get() for k, v in win.checks.items()})
                        self._values = values
                        self._on_action(aid, values)

                    return handler

                tk.Button(
                    root,
                    text=w.get("text", "OK"),
                    command=make_handler(),
                    bg=ACCENT,
                    fg="#ffffff",
                    relief="flat",
                    padx=10,
                    pady=4,
                ).pack(padx=12, pady=(6, 12))

    def _on_event(self, win, event, data):
        pass  # this panel is form-driven (button clicks), not event-fed - no external post() traffic expected

    def show(self) -> None:
        self._window = TkWindow(
            title=self._spec.get("title", "Ultron"),
            build=self._build,
            on_event=self._on_event,
            size=self._spec.get("size", "420x480"),
        )
        self._window.start()
        self._window.wait_ready()

    def close(self) -> None:
        if self._window:
            self._window.close()

    def get_values(self) -> Dict:
        return dict(self._values)


def build_panel(spec: Dict, on_action: Optional[Callable[[str, Dict], None]] = None) -> GeneratedPanel:
    """Validate `spec` at a basic level (title + widgets list present, all
    widget types recognized) and return a GeneratedPanel ready to
    .show(). Does not render anything until show() is called, so a
    caller can inspect/modify the spec first if needed."""
    if "widgets" not in spec or not isinstance(spec["widgets"], list):
        raise ValueError("Generative UI spec needs a 'widgets' list")
    return GeneratedPanel(spec, on_action=on_action)
