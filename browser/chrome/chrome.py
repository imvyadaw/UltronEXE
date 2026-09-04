"""Chrome automation
==================
Tab list/close, scroll, navigate, type, zoom, and YouTube control via UI Automation.
"""

import time
from typing import Dict, List

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    from pywinauto import Desktop

    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


class ChromeController:
    """Chrome tab/scroll/navigate/zoom control plus YouTube playback control."""

    def open_url(self, url: str) -> Dict:
        """Open a URL in the default browser."""
        import webbrowser

        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return {"success": True, "url": url}
        except Exception as e:
            return {"error": str(e)}

    def open_urls(self, urls: List[str]) -> Dict:
        """Open multiple URLs, each in a new browser tab."""
        import webbrowser

        try:
            results = []
            for url in urls:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                webbrowser.open_new_tab(url)
                results.append(url)
            return {"success": True, "opened": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    def _focus_chrome(self) -> bool:
        """Bring the Chrome window to the foreground. Returns True if found."""
        if not HAS_PYGETWINDOW:
            return False
        try:
            windows = [w for w in gw.getAllWindows() if "Chrome" in w.title and w.title.strip()]
            if not windows:
                return False
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def list_chrome_tabs(self) -> Dict:
        """List all open tabs in Chrome (via UI Automation)."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            chrome_win = desktop.window(class_name="Chrome_WidgetWin_1")
            if not chrome_win.exists(timeout=2):
                return {"error": "Chrome window not found - is Chrome open?"}

            tabs = []
            for i, tab in enumerate(chrome_win.descendants(control_type="TabItem")):
                name = tab.window_text()
                if name:
                    tabs.append({"tab": i + 1, "title": name})

            return {"tabs": tabs, "count": len(tabs)}
        except Exception as e:
            return {"error": f"Couldn't read Chrome tabs: {e}"}

    def close_chrome_tab(self, tab_identifier: str) -> Dict:
        """Close a Chrome tab by matching its title."""
        if not HAS_PYWINAUTO or not HAS_PYAUTOGUI:
            return {"error": "pywinauto/pyautogui not installed - run: pip install pywinauto pyautogui"}
        try:
            desktop = Desktop(backend="uia")
            chrome_win = desktop.window(class_name="Chrome_WidgetWin_1")
            if not chrome_win.exists(timeout=2):
                return {"error": "Chrome window not found - is Chrome open?"}

            identifier_lower = tab_identifier.lower()
            for tab in chrome_win.descendants(control_type="TabItem"):
                title = tab.window_text()
                if identifier_lower in title.lower():
                    tab.click_input()
                    time.sleep(0.2)
                    pyautogui.hotkey("ctrl", "w")
                    return {"success": True, "closed": title}

            return {"success": False, "error": f"No tab found matching '{tab_identifier}'"}
        except Exception as e:
            return {"error": str(e)}

    def close_chrome_tabs(self, tabs: List[str]) -> Dict:
        """Close multiple Chrome tabs by title match."""
        closed, failed = [], []
        for tab_id in tabs:
            result = self.close_chrome_tab(tab_id)
            if result.get("success"):
                closed.append(result.get("closed", tab_id))
            else:
                failed.append(tab_id)
        return {"success": len(closed) > 0, "closed": closed, "failed": failed, "count": len(closed)}

    def scroll_chrome(self, direction: str = "down", amount: int = 300) -> Dict:
        """Scroll in the active Chrome tab. Direction: up, down, left, right, top, bottom."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            direction = direction.lower()
            clicks = max(1, amount // 100)
            if direction == "up":
                pyautogui.scroll(clicks)
            elif direction == "down":
                pyautogui.scroll(-clicks)
            elif direction == "top":
                pyautogui.hotkey("ctrl", "home")
            elif direction == "bottom":
                pyautogui.hotkey("ctrl", "end")
            elif direction == "left":
                pyautogui.hscroll(-clicks)
            elif direction == "right":
                pyautogui.hscroll(clicks)
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}

    def chrome_navigate(self, action: str) -> Dict:
        """Navigate in Chrome: back, forward, refresh, or a URL."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            action_lower = action.lower()
            if action_lower == "back":
                pyautogui.hotkey("alt", "left")
            elif action_lower == "forward":
                pyautogui.hotkey("alt", "right")
            elif action_lower in ("refresh", "reload"):
                pyautogui.press("f5")
            else:
                url = action if action.startswith(("http://", "https://")) else f"https://{action}"
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.15)
                pyautogui.typewrite(url, interval=0.01)
                pyautogui.press("enter")
            return {"success": True, "action": action}
        except Exception as e:
            return {"error": str(e)}

    def type_in_chrome(self, text: str) -> Dict:
        """Type text into the currently focused element in Chrome."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}

    def chrome_keypress(self, key: str) -> Dict:
        """Press a key in Chrome: enter, escape, tab, space, etc."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            key_map = {
                "enter": "enter",
                "escape": "esc",
                "esc": "esc",
                "tab": "tab",
                "space": "space",
                "delete": "delete",
                "backspace": "backspace",
                "up": "up",
                "down": "down",
                "left": "left",
                "right": "right",
            }
            pyautogui.press(key_map.get(key.lower(), key.lower()))
            return {"success": True, "key": key}
        except Exception as e:
            return {"error": str(e)}

    def chrome_zoom(self, action: str) -> Dict:
        """Zoom in/out/reset in Chrome."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            action_lower = action.lower()
            if action_lower == "in":
                pyautogui.hotkey("ctrl", "+")
            elif action_lower == "out":
                pyautogui.hotkey("ctrl", "-")
            else:
                pyautogui.hotkey("ctrl", "0")
            return {"success": True, "zoom": action}
        except Exception as e:
            return {"error": str(e)}

    def youtube_search(self, query: str) -> Dict:
        """Open YouTube and search for a query."""
        import webbrowser

        try:
            encoded_query = query.replace(" ", "+")
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            webbrowser.open(url)
            return {"success": True, "searched": query}
        except Exception as e:
            return {"error": str(e)}

    def youtube_play(self, query: str) -> Dict:
        """Search YouTube and actually play the top result (unlike
        youtube_search, which only opens the search-results page). Scrapes
        the top video ID out of the search-results HTML - no API key
        needed - and opens its watch URL directly, which auto-plays."""
        import re
        import webbrowser

        try:
            import requests as _requests
        except ImportError:
            _requests = None
        try:
            encoded_query = query.replace(" ", "+")
            search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
            video_id = None
            if _requests is not None:
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    resp = _requests.get(search_url, headers=headers, timeout=8)
                    if resp.status_code == 200:
                        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
                        if match:
                            video_id = match.group(1)
                except Exception:
                    video_id = None
            if video_id:
                watch_url = f"https://www.youtube.com/watch?v={video_id}"
                webbrowser.open(watch_url)
                return {"success": True, "played": query, "video_id": video_id, "url": watch_url}
            # Fallback: couldn't scrape a video ID (offline / blocked / no
            # requests) - open the search page so the user isn't left with
            # nothing, but be honest that it didn't auto-play.
            webbrowser.open(search_url)
            return {
                "success": True,
                "played": query,
                "video_id": None,
                "note": "couldn't resolve a specific video to auto-play - opened the search results instead",
            }
        except Exception as e:
            return {"error": str(e)}

    def youtube_control(self, action: str) -> Dict:
        """Control YouTube playback via its native keyboard shortcuts."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_chrome():
            return {"error": "Chrome window not found - is Chrome open?"}
        try:
            action_key = action.lower().replace(" ", "")
            key_actions = {
                "play": lambda: pyautogui.press("k"),
                "pause": lambda: pyautogui.press("k"),
                "toggle": lambda: pyautogui.press("k"),
                "mute": lambda: pyautogui.press("m"),
                "unmute": lambda: pyautogui.press("m"),
                "fullscreen": lambda: pyautogui.press("f"),
                "skip": lambda: pyautogui.press("l"),
                "rewind": lambda: pyautogui.press("j"),
                "volumeup": lambda: pyautogui.press("up"),
                "volumedown": lambda: pyautogui.press("down"),
            }
            key_actions.get(action_key, key_actions["toggle"])()
            return {"success": True, "action": action}
        except Exception as e:
            return {"error": str(e)}
