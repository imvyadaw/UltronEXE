"""
Spatial memory
==============
"Where" memory - genuinely new, nothing in memory/ tracks this today.
A place can be:

    - "geo"       a real-world location (lat/lon, e.g. from a future
                   location-aware skill) - "home", "office"
    - "filesystem" a path Ultron cares about - "Downloads folder",
                   "the project repo" - skills/file/ and skills/data/
                   already operate on paths but never name/remember
                   them as places
    - "app"        a named application/window context -
                   agents/windows_agent.py and skills/app_control/
                   already act on apps by name; this is where "the
                   place" an episodic event happened can point when
                   that place is "inside VS Code" rather than physical
    - "network"    a host/endpoint - networking/ssh_client.py,
                   networking/ftp_client.py etc. connect to hosts by
                   address already; this lets a host be named and
                   recalled like any other place

Every place is also a memory_graph.py node ("place:<id>"), so
episodic_memory.py events can be linked to where they happened via
link_event_to_place(), and later queried either way: "what places do I
use most" or "what happened at the office".
"""

import math
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from advanced_memory.memory_graph import get_memory_graph
from advanced_memory.forgetting_curve import get_forgetting_curve

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "spatial_memory.db"

VALID_TYPES = {"geo", "filesystem", "app", "network"}

_spatial: Optional["SpatialMemory"] = None
_lock = Lock()


class SpatialMemory:
    """Named places, of any of VALID_TYPES, plus what happened at
    them. Do not construct directly - use get_spatial_memory()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                place_type TEXT,
                locator TEXT,
                latitude REAL,
                longitude REAL,
                notes TEXT,
                created_at REAL,
                UNIQUE(name, place_type)
            )""")
        self._conn.commit()
        self._write_lock = Lock()

        self._graph = get_memory_graph()
        self._curve = get_forgetting_curve()

    # -- writing ---------------------------------------------------------------
    def remember_place(
        self,
        name: str,
        place_type: str,
        locator: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        notes: str = "",
    ) -> Dict:
        """Name a place. `locator` is the type-specific address: a
        filesystem path, an app/window identifier, or a hostname -
        lat/lon are only meaningful for place_type="geo"."""
        if place_type not in VALID_TYPES:
            return {"error": f"place_type must be one of {sorted(VALID_TYPES)}"}
        try:
            with self._write_lock:
                cur = self._conn.execute(
                    "INSERT INTO places (name, place_type, locator, latitude, longitude, notes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(name, place_type) DO UPDATE SET locator = excluded.locator, "
                    "latitude = excluded.latitude, longitude = excluded.longitude, notes = excluded.notes",
                    (name, place_type, locator, latitude, longitude, notes, time.time()),
                )
                self._conn.commit()
            row = self._get_row_by_name(name, place_type)
            place_id = row["id"]
            node_id = f"place:{place_id}"
            self._graph.add_node(node_id, "spatial", name, metadata={"place_type": place_type, "locator": locator})
            self._curve.track(node_id, importance=0.5)
            return {"success": True, "id": place_id, "node_id": node_id, "name": name, "place_type": place_type}
        except Exception as e:
            return {"error": str(e)}

    def link_event_to_place(self, event_id: int, place_id: int, relation: str = "occurred_at") -> Dict:
        """Connects an episodic_memory.py event to a place here -
        callers typically pass this through
        episodic_memory.AdvancedEpisodicMemory.link_event() instead of
        calling memory_graph directly, but this wrapper keeps the
        relation name consistent across every caller."""
        return self._graph.add_edge(f"episodic:{event_id}", f"place:{place_id}", relation)

    # -- reading -----------------------------------------------------------------
    def get_place(self, name: str, place_type: Optional[str] = None) -> Dict:
        try:
            cur = self._conn.cursor()
            if place_type:
                cur.execute(
                    "SELECT id, name, place_type, locator, latitude, longitude, notes, created_at FROM places WHERE name = ? AND place_type = ?",
                    (name, place_type),
                )
            else:
                cur.execute(
                    "SELECT id, name, place_type, locator, latitude, longitude, notes, created_at FROM places WHERE name = ?",
                    (name,),
                )
            row = cur.fetchone()
            if not row:
                return {"error": f"No place named '{name}'"}
            place_id = row[0]
            self._curve.record_access(f"place:{place_id}")
            return self._row_to_dict(row)
        except Exception as e:
            return {"error": str(e)}

    def list_places(self, place_type: Optional[str] = None) -> Dict:
        try:
            cur = self._conn.cursor()
            if place_type:
                cur.execute(
                    "SELECT id, name, place_type, locator, latitude, longitude, notes, created_at FROM places WHERE place_type = ?",
                    (place_type,),
                )
            else:
                cur.execute("SELECT id, name, place_type, locator, latitude, longitude, notes, created_at FROM places")
            rows = cur.fetchall()
            places = [self._row_to_dict(r) for r in rows]
            return {"count": len(places), "places": places}
        except Exception as e:
            return {"error": str(e)}

    def events_at_place(self, place_id: int) -> Dict:
        """Every episodic event linked to this place via
        link_event_to_place() / episodic_memory.py's link_event()."""
        nb = self._graph.neighbors(f"place:{place_id}", direction="in")
        if "error" in nb:
            return nb
        event_ids = [n["node_id"].split(":", 1)[1] for n in nb["neighbors"] if n["node_id"].startswith("episodic:")]
        return {"place_id": place_id, "count": len(event_ids), "event_ids": event_ids}

    def nearby_geo_places(self, latitude: float, longitude: float, radius_km: float = 5.0) -> Dict:
        """Places of type "geo" within `radius_km` of a point, using the
        haversine formula - fine at personal-assistant scale (a handful
        of named places), no need for a spatial index."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, name, place_type, locator, latitude, longitude, notes FROM places WHERE place_type = 'geo' AND latitude IS NOT NULL AND longitude IS NOT NULL"
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                dist = _haversine_km(latitude, longitude, r[4], r[5])
                if dist <= radius_km:
                    d = self._row_to_dict((r[0], r[1], r[2], r[3], r[4], r[5], r[6], None))
                    d["distance_km"] = round(dist, 3)
                    results.append(d)
            results.sort(key=lambda x: x["distance_km"])
            return {"count": len(results), "places": results}
        except Exception as e:
            return {"error": str(e)}

    # -- internal --------------------------------------------------------------
    def _get_row_by_name(self, name: str, place_type: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, name, place_type, locator, latitude, longitude, notes, created_at FROM places WHERE name = ? AND place_type = ?",
            (name, place_type),
        )
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "name": row[1],
            "place_type": row[2],
            "locator": row[3],
            "latitude": row[4],
            "longitude": row[5],
            "notes": row[6],
            "created_at": row[7],
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_spatial_memory() -> SpatialMemory:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _spatial
    with _lock:
        if _spatial is None:
            _spatial = SpatialMemory()
        return _spatial
