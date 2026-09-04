"""
WhatsApp automation
=====================
Two ways to send a message, depending on what the caller has:

- send_message(phone, message) - phone number known. Uses the wa.me deep
  link (opens WhatsApp Desktop if installed, else WhatsApp Web) which
  supports pre-filling a chat + message text. Actually pressing Send still
  needs a UI keystroke since wa.me has no "send immediately" parameter -
  send_message() waits for the chat to load then presses Enter.

- send_message_by_name(name, message) - only a contact NAME is known (the
  normal case for a voice/text command like "message Sachin Yadav on
  WhatsApp"). This drives WhatsApp Desktop's own "New chat" contact search
  via UI Automation (pywinauto) instead of guessing/hallucinating a phone
  number - see find_chat_matches() below. If more than one saved contact
  shares that exact name, it returns the candidates instead of guessing
  which one, so the caller (ai/tool_runtime.py's tool loop) can ask the
  user to confirm before a second call with match_index set.
"""

import time
import webbrowser
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp

_UIA_TIMEOUT = 6
_SEARCH_SETTLE_SECONDS = 0.9
_CHAT_LOAD_SECONDS = 0.8


class WhatsAppApp(BaseApp):
    """Open chats and send messages via WhatsApp Desktop/Web."""

    APP_NAME = "whatsapp"
    PROCESS_NAMES = ["whatsapp.exe", "whatsapp"]
    EXE_HINTS = ["whatsapp", "whatsapp.exe"]

    # -- phone-number path (wa.me deep link) --------------------------------
    def open_chat(self, phone: str, message: Optional[str] = None) -> Dict:
        try:
            url = f"https://wa.me/{phone.lstrip('+')}"
            if message:
                url += f"?text={quote(message)}"
            webbrowser.open(url)
            return {"success": True, "phone": phone}
        except Exception as e:
            return {"error": str(e)}

    def send_message(self, phone: str, message: str, wait_seconds: float = 6.0) -> Dict:
        """Opens the chat pre-filled with the message, waits for it to load,
        then presses Enter to send. wait_seconds should cover WhatsApp
        Web/Desktop's load time on the caller's machine."""
        opened = self.open_chat(phone, message)
        if opened.get("error"):
            return opened
        time.sleep(wait_seconds)
        sent = self.press_key("enter")
        return {**opened, "sent": not sent.get("error"), "message": message}

    # -- name-based path (WhatsApp Desktop UI Automation) --------------------
    def _connect_uia_window(self):
        """Best-effort handle to the live WhatsApp Desktop main window via
        pywinauto's UIA backend. Raises RuntimeError with a clear reason on
        failure (pywinauto missing, WhatsApp not open, or its window has no
        accessible UI tree) - callers turn that into an {"error": ...} dict
        rather than letting the exception bubble up."""
        try:
            from pywinauto import Application
        except ImportError as e:
            raise RuntimeError("pywinauto not installed - run: pip install pywinauto pywin32") from e

        try:
            app = Application(backend="uia").connect(title_re=".*WhatsApp.*", timeout=_UIA_TIMEOUT)
            return app.top_window()
        except Exception as e:
            raise RuntimeError(
                f"Could not attach to the WhatsApp Desktop window ({e}). "
                "Make sure WhatsApp Desktop (not just WhatsApp Web in a browser tab) is open."
            ) from e

    def _open_new_chat_search(self, window) -> None:
        """Open WhatsApp Desktop's 'New chat' contact-search panel (the one
        that can find ANY saved contact by name, not just chats you already
        have open) and land focus in its search box."""
        # Try clicking a "New chat" button first - most reliable when the
        # accessible name is exposed. Falls back to the Ctrl+Alt+N shortcut
        # WhatsApp Desktop ships with if no such button is found.
        try:
            btn = window.child_window(title_re="New chat.*", control_type="Button")
            btn.click_input()
        except Exception:
            self.press_key("ctrl+alt+n")
        time.sleep(0.6)

    def _find_search_box(self, window):
        """The contact-search text box inside the New chat panel. WhatsApp
        Desktop labels it a few different ways across versions/locales, so
        try each in turn before giving up."""
        for title_re in ("Search name or number.*", "Search.*", ".*"):
            try:
                box = window.child_window(title_re=title_re, control_type="Edit", found_index=0)
                if box.exists():
                    return box
            except Exception:
                continue
        raise RuntimeError("Couldn't find the contact search box in WhatsApp's New chat panel.")

    def find_chat_matches(self, name: str) -> Dict:
        """Open New chat, search `name`, and return every result WhatsApp's
        own contact search shows for it - without clicking or sending
        anything. Used internally by send_message_by_name(), also exposed
        as its own tool so the AI can list matches for the user without
        committing to sending a message yet."""
        try:
            window = self._connect_uia_window()
            self._open_new_chat_search(window)
            search_box = self._find_search_box(window)
            search_box.set_focus()
            search_box.set_text("")
            search_box.type_keys(name, with_spaces=True)
            time.sleep(_SEARCH_SETTLE_SECONDS)

            items = window.descendants(control_type="ListItem")
            matches = []
            for item in items:
                try:
                    text = item.window_text().strip()
                except Exception:
                    continue
                if text:
                    matches.append(text)
            return {"success": True, "query": name, "matches": matches}
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"WhatsApp contact search failed: {e}"}

    def send_message_by_name(self, name: str, message: str, match_index: Optional[int] = None) -> Dict:
        """Search WhatsApp Desktop's New chat panel for `name` and send
        `message` to it.

        - 0 matches            -> {"error": "..."} - contact doesn't exist
                                   under that name in WhatsApp; caller should
                                   tell the user, not invent a phone number.
        - 1 unambiguous match   -> sends immediately.
        - 2+ matches with the
          SAME name             -> returns {"success": False,
                                   "needs_confirmation": True, "matches": [...]}
                                   instead of guessing. The caller (the AI)
                                   should ask the user which one, then call
                                   this again with match_index set to their
                                   choice (0-based, into the returned list).
        - match_index passed    -> skips disambiguation and clicks that
                                   result directly (used for the confirmed
                                   follow-up call above).
        """
        try:
            if not self.is_running().get("running"):
                opened = self.open()
                if opened.get("error"):
                    return opened
                self.wait_for_window(timeout=15)
                time.sleep(1.0)

            window = self._connect_uia_window()
            self._open_new_chat_search(window)
            search_box = self._find_search_box(window)
            search_box.set_focus()
            search_box.set_text("")
            search_box.type_keys(name, with_spaces=True)
            time.sleep(_SEARCH_SETTLE_SECONDS)

            result_items = [i for i in window.descendants(control_type="ListItem") if i.window_text().strip()]

            if not result_items:
                return {"success": False, "error": f"No WhatsApp contact named '{name}' was found."}

            if match_index is not None:
                if not (0 <= match_index < len(result_items)):
                    return {"error": f"match_index {match_index} out of range (0-{len(result_items) - 1})."}
                chosen = result_items[match_index]
            elif len(result_items) == 1:
                chosen = result_items[0]
            else:
                same_name = [i for i in result_items if i.window_text().strip().lower() == name.strip().lower()]
                if len(same_name) > 1:
                    return {
                        "success": False,
                        "needs_confirmation": True,
                        "query": name,
                        "matches": [i.window_text().strip() for i in same_name],
                        "message": (
                            f"{len(same_name)} WhatsApp contacts are named '{name}'. "
                            "Ask the user which one they mean, then call this tool again "
                            "with match_index set to their choice (0-based)."
                        ),
                    }
                # Only one of the results is actually named exactly `name`
                # (the rest are loose/partial matches WhatsApp's own search
                # also surfaced) - safe to pick it without asking.
                chosen = same_name[0] if same_name else result_items[0]

            chosen_name = chosen.window_text().strip()
            chosen.click_input()
            time.sleep(_CHAT_LOAD_SECONDS)

            typed = self.type_text(message)
            if typed.get("error"):
                return typed
            time.sleep(0.15)
            sent = self.press_key("enter")

            return {"success": not sent.get("error"), "sent_to": chosen_name, "message": message}
        except RuntimeError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"WhatsApp send_message_by_name failed: {e}"}
