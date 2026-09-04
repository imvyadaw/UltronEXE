"""UI element automation
======================
Find and click UI elements (buttons, menu items, text fields) by their
visible name/text, across any application window - using pywinauto's
UI Automation backend (same library already used for Chrome tab
control in browser/chrome/chrome.py).
"""

from typing import Dict

try:
    from pywinauto import Desktop

    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


class UIAutomation:
    """Find/click UI elements by name in any open window."""

    def find_element(self, element_name: str, window_title: str = None) -> Dict:
        """Find a UI element by its visible name, optionally scoped to a window title."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            if window_title:
                windows = [w for w in desktop.windows() if window_title.lower() in w.window_text().lower()]
            else:
                windows = desktop.windows()

            for win in windows:
                try:
                    for elem in win.descendants(title=element_name):
                        rect = elem.rectangle()
                        return {
                            "found": True,
                            "name": elem.window_text(),
                            "control_type": elem.element_info.control_type,
                            "window": win.window_text(),
                            "position": {
                                "left": rect.left,
                                "top": rect.top,
                                "right": rect.right,
                                "bottom": rect.bottom,
                            },
                        }
                except Exception:
                    continue
            return {"found": False, "error": f"No element named '{element_name}' found"}
        except Exception as e:
            return {"error": str(e)}

    def click_element(self, element_name: str, window_title: str = None) -> Dict:
        """Find and click a UI element by its visible name."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            if window_title:
                windows = [w for w in desktop.windows() if window_title.lower() in w.window_text().lower()]
            else:
                windows = desktop.windows()

            for win in windows:
                try:
                    for elem in win.descendants(title=element_name):
                        elem.click_input()
                        return {"success": True, "clicked": element_name, "window": win.window_text()}
                except Exception:
                    continue
            return {"success": False, "error": f"No clickable element named '{element_name}' found"}
        except Exception as e:
            return {"error": str(e)}

    def activate_window(self, window_title: str) -> Dict:
        """Bring any open window to the foreground by (partial) title match -
        generic version of what browser/chrome/edge/firefox each do for
        themselves, but works for any app (Photoshop, Excel, Notepad, a
        random game, whatever's open)."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            windows = [w for w in desktop.windows() if window_title.lower() in w.window_text().lower()]
            if not windows:
                return {"success": False, "error": f"No window found matching '{window_title}'"}
            windows[0].set_focus()
            return {"success": True, "activated": windows[0].window_text()}
        except Exception as e:
            return {"error": str(e)}

    def type_into_element(self, element_name: str, text: str, window_title: str = None) -> Dict:
        """Click a named field/element (a text box, search bar, etc.) in any
        window, then type text into it. This is what lets Ultron fill in
        forms/fields inside apps that aren't Chrome/Edge/Firefox, which
        only have their own bespoke type-in helpers."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        click_result = self.click_element(element_name, window_title=window_title)
        if not click_result.get("success"):
            return click_result
        try:
            import pyautogui

            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text, "into": element_name}
        except ImportError:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        except Exception as e:
            return {"error": str(e)}

    def list_elements(self, window_title: str, control_type: str = None) -> Dict:
        """List all UI elements in a window, optionally filtered by control type
        (e.g. 'Button', 'Edit', 'MenuItem')."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            windows = [w for w in desktop.windows() if window_title.lower() in w.window_text().lower()]
            if not windows:
                return {"error": f"No window found matching '{window_title}'"}

            elements = []
            kwargs = {"control_type": control_type} if control_type else {}
            for elem in windows[0].descendants(**kwargs):
                name = elem.window_text()
                if name:
                    elements.append({"name": name, "control_type": elem.element_info.control_type})
            return {"window": windows[0].window_text(), "count": len(elements), "elements": elements[:100]}
        except Exception as e:
            return {"error": str(e)}
