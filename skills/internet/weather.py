"""Weather lookup
===============
Quick weather lookup via wttr.in - no API key needed.
"""

from typing import Dict

try:
    import requests as _requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class WeatherLookup:
    def get_weather(self, location: str = "") -> Dict:
        """Get current weather for a location (blank = auto-detect by IP)."""
        if not HAS_REQUESTS:
            return {"error": "requests not installed - run: pip install requests"}
        try:
            url = f"https://wttr.in/{location}?format=3" if location else "https://wttr.in/?format=3"
            resp = _requests.get(url, timeout=8)
            if resp.status_code == 200:
                return {"weather": resp.text.strip()}
            return {"error": f"Weather service returned status {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}
