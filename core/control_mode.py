"""
Control Mode (User Trust Override)
===================================
Two blanket .env switches for the user's OWN machine, sitting above every
other gate in approval/, safety/ and core/permissions.py:

  ULTRON_SAFE_CONTROL=true|false
      Category = everything NOT in PermissionGate.DESTRUCTIVE_TOOLS
      (open apps, type/click, volume/brightness, read files, browse web,
      notifications, "medium" risk stuff like send_email/make_purchase...).
      When true: these run immediately, without waiting on
      trust_policy's learned-confidence ramp-up (safety/learning_policy.py
      sample-size gate is skipped).

  ULTRON_UNSAFE_CONTROL=true|false
      Category = PermissionGate.DESTRUCTIVE_TOOLS itself - delete_file,
      delete_folder, shutdown_pc, kill_process, run_command,
      run_powershell, registry writes, etc. Irreversible or hard-to-
      reverse actions.
      When true: these run immediately too, with NO confirmation prompt.

Both default to False - untouched, current safe-by-default behaviour.
Setting a flag to true means "I trust myself/Ultron enough that this
whole category should run unattended." It does NOT disable logging -
every gated call still goes through core/logger.py, so there's always
an audit trail of what ran on its own, even with both flags on.

These two flags are deliberately coarse (2 categories, exactly as
requested) rather than per-tool. If finer control is ever wanted later,
pin individual tools with safety/trust_policy.py's TrustPolicy.pin()
instead of adding more env vars here.

Read fresh from os.environ on every call (no caching) so flipping .env
and restarting Ultron is enough - nothing else to invalidate.
"""

import os
import threading
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Defensive: config.py already calls load_dotenv() on import and this
# module is normally imported after it, but if something ever imports
# control_mode.py first (e.g. a standalone script), .env would silently
# not be loaded and both flags would read as their "false" default -
# loading here too (find_dotenv-free, same fixed path as config.py) costs
# nothing extra since python-dotenv no-ops on an already-loaded var.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# --- runtime override (this session only) --------------------------------
# .env flags need an editor + restart to flip. That's fine friction for
# the UNSAFE category (destructive tools skipping confirmation entirely
# deserves it - deliberately NOT given a runtime/voice override below).
# For the SAFE category, a spoken "auto mode on" / "sab khud kar do"
# mid-session is a reasonable ask, so this in-memory override lets
# Assistant._apply_action() flip it instantly, no .env edit or restart.
# None means "no override this session - fall back to whatever .env
# says". Deliberately process-local and resets to None on every
# restart, so a forgotten "auto mode on" from last night can never
# silently carry over into a new session.
_lock = threading.Lock()
_safe_override: Optional[bool] = None


def set_safe_control_override(enabled: Optional[bool]) -> None:
    """Flip ULTRON_SAFE_CONTROL for the rest of this run without touching
    .env. Pass None to clear the override and go back to reading .env."""
    global _safe_override
    with _lock:
        _safe_override = enabled


def get_safe_control_override() -> Optional[bool]:
    with _lock:
        return _safe_override


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "on")


def safe_control_enabled() -> bool:
    """True => non-destructive / low+medium risk actions auto-run,
    bypassing the learned-confidence ramp-up in safety/trust_policy.py.
    Checks this session's runtime override first (set via the "auto
    mode on/off" command), then falls back to the .env flag."""
    override = get_safe_control_override()
    if override is not None:
        return override
    return _flag("ULTRON_SAFE_CONTROL")


def unsafe_control_enabled() -> bool:
    """True => PermissionGate.DESTRUCTIVE_TOOLS actions auto-run with
    zero confirmation prompt. Irreversible actions included. Use with
    real intent, not just to silence prompts you haven't read.
    Deliberately .env-only (no runtime/voice override) - a spoken
    phrase should never be able to disable confirmation on
    delete/shutdown/run_command-class actions for the rest of a
    session."""
    return _flag("ULTRON_UNSAFE_CONTROL")
