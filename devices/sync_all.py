"""
Sync All (DEVICES)
======================
The read side of this package, mirroring routine.py's role on the
HOME side: one call that fans out across phone_link.py, watch_link.py,
tv_control.py and car_link.py and comes back with a single snapshot,
rather than a caller polling all four separately. Nothing here writes
anything - it's status only. A `notify_all()` companion is included
for the one write-ish action that's genuinely common across device
types: pushing the same message to every paired phone and watch at
once (e.g. "leaving now" from a HOME routine).

Each module's status is gathered independently and a failure reading
one (an exception from a module this build doesn't fully have set
up) is captured per-module rather than aborting the whole snapshot -
the same best-effort, collect-everything approach routine.py uses
for writes.
"""

from typing import Callable, Dict, Optional

from devices.phone_link import get_phone_link
from devices.watch_link import get_watch_link
from devices.tv_control import get_tv_control
from devices.car_link import get_car_link


class SyncAll:
    """Cross-module status snapshot + broadcast notify. Use
    get_sync_all()."""

    def _safe(self, label: str, fn: Callable[[], Dict]) -> Dict:
        try:
            return fn()
        except Exception as exc:
            return {"error": str(exc)}

    def snapshot(self) -> Dict:
        """One status pull across every DEVICES module. Returns
        {"phones": dict, "watches": dict, "tvs": dict, "cars": dict},
        where each value maps that module's device IDs to whatever
        that module already tracks (paired/locked/on/etc.) - this
        function adds no new state of its own."""
        phone_link = get_phone_link()
        watch_link = get_watch_link()
        tv = get_tv_control()
        car = get_car_link()

        return {
            "phones": self._safe(
                "phones",
                lambda: {
                    pid: {"paired": phone_link.is_paired(pid), "queued": len(phone_link.get_queued(pid, clear=False))}
                    for pid in phone_link.list_phones()
                },
            ),
            "watches": self._safe(
                "watches",
                lambda: {
                    wid: {
                        "paired": watch_link.is_paired(wid),
                        "latest_heart_rate": watch_link.get_latest(wid, "heart_rate"),
                        "latest_battery": watch_link.get_latest(wid, "battery"),
                    }
                    for wid in watch_link.list_watches()
                },
            ),
            "tvs": self._safe("tvs", lambda: {tid: tv.get_state(tid) for tid in tv.list_tvs()}),
            "cars": self._safe(
                "cars",
                lambda: {cid: {"locked": car.is_locked(cid), "location": car.locate(cid)} for cid in car.list_cars()},
            ),
        }

    def notify_all(self, title: str, message: str) -> Dict:
        """Pushes the same notification to every paired phone and
        watch. Per-device failures (e.g. one phone unpaired mid-list)
        don't stop the rest from being attempted. Returns
        {"phones": Dict[str, dict], "watches": Dict[str, dict]},
        each mapping device id to that call's own result dict."""
        phone_link = get_phone_link()
        watch_link = get_watch_link()

        phone_results = {}
        for pid in phone_link.list_phones():
            if phone_link.is_paired(pid):
                phone_results[pid] = self._safe(pid, lambda pid=pid: phone_link.notify(pid, title, message))

        watch_results = {}
        for wid in watch_link.list_watches():
            if watch_link.is_paired(wid):
                watch_results[wid] = self._safe(wid, lambda wid=wid: watch_link.notify(wid, title, message))

        return {"phones": phone_results, "watches": watch_results}


_sync_all: Optional[SyncAll] = None


def get_sync_all() -> SyncAll:
    global _sync_all
    if _sync_all is None:
        _sync_all = SyncAll()
    return _sync_all
