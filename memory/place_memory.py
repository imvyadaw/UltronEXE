"""
Place Memory
============
Named locations ("home", "office", "mom's house") tied to whatever
signal is available - GPS coordinates, a Wi-Fi SSID, or both - so
"you're at the office" or a proactive "want me to start your work
playlist?" can be grounded in *this specific place*, not just "not
home". Matches the location-signal shape already implied by this
project's Android build (a phone is the realistic source of GPS/SSID
readings, not a desktop) - if no location provider is wired up yet,
current_place() degrades to None like everything else in this phase
that depends on hardware not yet connected.

Matching is deliberately simple: an exact Wi-Fi SSID match wins
outright (most reliable signal indoors); otherwise the closest known
place within PLACE_RADIUS_METERS by GPS wins. No fuzzy matching, no
ML - a wrong guess here would be worse than no guess.
"""

import math
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "place_memory.db"
PLACE_RADIUS_METERS = 150


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class PlaceMemory:
    """Named places + a visit log. Use get_place_memory()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS places (
                    name TEXT PRIMARY KEY, lat REAL, lon REAL, wifi_ssid TEXT, note TEXT
                )""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, place TEXT, arrived_at REAL
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._places: Dict[str, Dict] = {}
            self._visits: List[Dict] = []

    def learn_place(
        self,
        name: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        wifi_ssid: Optional[str] = None,
        note: str = "",
    ) -> Dict:
        if not self._db_ok:
            self._places[name] = {"name": name, "lat": lat, "lon": lon, "wifi_ssid": wifi_ssid, "note": note}
            return self._places[name]
        self._conn.execute(
            "INSERT INTO places (name, lat, lon, wifi_ssid, note) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, "
            "wifi_ssid=excluded.wifi_ssid, note=excluded.note",
            (name, lat, lon, wifi_ssid, note),
        )
        self._conn.commit()
        return {"name": name, "lat": lat, "lon": lon, "wifi_ssid": wifi_ssid, "note": note}

    def current_place(
        self, lat: Optional[float] = None, lon: Optional[float] = None, wifi_ssid: Optional[str] = None
    ) -> Optional[str]:
        """Best-guess match from whichever signal(s) are given. SSID
        match wins outright; otherwise nearest known place by GPS,
        only if within PLACE_RADIUS_METERS. Logs a visit on any match."""
        places = self.known_places()

        if wifi_ssid:
            for p in places:
                if p.get("wifi_ssid") and p["wifi_ssid"] == wifi_ssid:
                    self._log_visit(p["name"])
                    return p["name"]

        if lat is not None and lon is not None:
            best_name, best_dist = None, PLACE_RADIUS_METERS
            for p in places:
                if p.get("lat") is None or p.get("lon") is None:
                    continue
                dist = _haversine_m(lat, lon, p["lat"], p["lon"])
                if dist <= best_dist:
                    best_name, best_dist = p["name"], dist
            if best_name:
                self._log_visit(best_name)
                return best_name

        return None

    def _log_visit(self, name: str) -> None:
        now = time.time()
        if not self._db_ok:
            self._visits.append({"place": name, "arrived_at": now})
            return
        self._conn.execute("INSERT INTO visits (place, arrived_at) VALUES (?, ?)", (name, now))
        self._conn.commit()

    def place_history(self, name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        if not self._db_ok:
            rows = [v for v in self._visits if name is None or v["place"] == name]
            return rows[-limit:]
        cur = self._conn.cursor()
        if name:
            cur.execute(
                "SELECT place, arrived_at FROM visits WHERE place=? ORDER BY arrived_at DESC LIMIT ?", (name, limit)
            )
        else:
            cur.execute("SELECT place, arrived_at FROM visits ORDER BY arrived_at DESC LIMIT ?", (limit,))
        return [{"place": r[0], "arrived_at": r[1]} for r in cur.fetchall()]

    def known_places(self) -> List[Dict]:
        if not self._db_ok:
            return list(self._places.values())
        cur = self._conn.cursor()
        cur.execute("SELECT name, lat, lon, wifi_ssid, note FROM places")
        cols = ["name", "lat", "lon", "wifi_ssid", "note"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- deletion primitive - forget.py is the only intended caller -----
    def _delete_place(self, name: str) -> bool:
        if not self._db_ok:
            existed = self._places.pop(name, None) is not None
            self._visits = [v for v in self._visits if v["place"] != name]
            return existed
        cur = self._conn.cursor()
        cur.execute("DELETE FROM places WHERE name=?", (name,))
        self._conn.execute("DELETE FROM visits WHERE place=?", (name,))
        self._conn.commit()
        return cur.rowcount > 0


_place_memory: Optional[PlaceMemory] = None


def get_place_memory() -> PlaceMemory:
    global _place_memory
    if _place_memory is None:
        _place_memory = PlaceMemory()
    return _place_memory
