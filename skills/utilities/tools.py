"""
Utility tools skill
====================
General-purpose helpers that don't belong to any single integration:
text transforms, unit conversion, date/time math, hashing/encoding, and
random generation. Unlike the other Phase 4 facades, there's no separate
lower-level module behind this one - these are new, self-contained, and
stdlib-only (no optional dependencies to install).
"""

import base64
import hashlib
import random
import re
import string
import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, Optional

from skills.base_skill import BaseSkill

_LENGTH_TO_METERS = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
}
_WEIGHT_TO_GRAMS = {
    "mg": 0.001,
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
}
_DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"]


class UtilityTools(BaseSkill):
    """Stdlib-only text, unit-conversion, date/time, hashing, and random helpers."""

    name = "utilities"
    description = "Text transforms, unit conversion, date/time math, hashing/encoding, and random generation."
    category = "utility"

    # -- text -------------------------------------------------------------
    def text_stats(self, text: str) -> Dict:
        words = text.split()
        return {
            "characters": len(text),
            "characters_no_spaces": len(text.replace(" ", "")),
            "words": len(words),
            "lines": len(text.splitlines()) or (1 if text else 0),
            "sentences": len(re.findall(r"[.!?]+", text)),
        }

    def slugify(self, text: str, separator: str = "-") -> Dict:
        slug = re.sub(r"[^a-z0-9]+", separator, text.lower()).strip(separator)
        return {"slug": slug}

    def truncate(self, text: str, max_length: int = 100, suffix: str = "...") -> Dict:
        if len(text) <= max_length:
            return {"truncated": text}
        cut = max_length - len(suffix)
        return {"truncated": text[: max(cut, 0)].rstrip() + suffix}

    def change_case(self, text: str, case: str = "upper") -> Dict:
        cases = {
            "upper": text.upper(),
            "lower": text.lower(),
            "title": text.title(),
            "capitalize": text.capitalize(),
            "swap": text.swapcase(),
        }
        if case not in cases:
            return {"success": False, "error": f"Unknown case '{case}' - use one of {list(cases)}"}
        return {"result": cases[case]}

    def similarity(self, text_a: str, text_b: str) -> Dict:
        """Rough 0-1 similarity ratio between two strings (difflib, stdlib-only)."""
        ratio = SequenceMatcher(None, text_a, text_b).ratio()
        return {"ratio": round(ratio, 4), "percent": round(ratio * 100, 1)}

    # -- unit conversion --------------------------------------------------
    def convert_length(self, value: float, from_unit: str, to_unit: str) -> Dict:
        try:
            meters = value * _LENGTH_TO_METERS[from_unit.lower()]
            result = meters / _LENGTH_TO_METERS[to_unit.lower()]
            return {"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": round(result, 6)}
        except KeyError as e:
            return {"success": False, "error": f"Unknown length unit {e}. Use one of {list(_LENGTH_TO_METERS)}"}

    def convert_weight(self, value: float, from_unit: str, to_unit: str) -> Dict:
        try:
            grams = value * _WEIGHT_TO_GRAMS[from_unit.lower()]
            result = grams / _WEIGHT_TO_GRAMS[to_unit.lower()]
            return {"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": round(result, 6)}
        except KeyError as e:
            return {"success": False, "error": f"Unknown weight unit {e}. Use one of {list(_WEIGHT_TO_GRAMS)}"}

    def convert_temperature(self, value: float, from_unit: str, to_unit: str) -> Dict:
        f, t = from_unit.lower(), to_unit.lower()
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}.get(f)
        if celsius is None:
            return {"success": False, "error": "from_unit must be 'c', 'f', or 'k'"}
        result = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}.get(t)
        if result is None:
            return {"success": False, "error": "to_unit must be 'c', 'f', or 'k'"}
        return {"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": round(result, 4)}

    # -- date / time --------------------------------------------------------
    def _parse(self, date_str: str) -> datetime:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not parse date '{date_str}' - try YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")

    def current_time(self, fmt: Optional[str] = None) -> Dict:
        now = datetime.now()
        return {"iso": now.isoformat(), "formatted": now.strftime(fmt) if fmt else now.strftime("%Y-%m-%d %H:%M:%S")}

    def add_time(self, date_str: str, days: int = 0, hours: int = 0, minutes: int = 0) -> Dict:
        dt = self._parse(date_str) + timedelta(days=days, hours=hours, minutes=minutes)
        return {"result": dt.strftime("%Y-%m-%d %H:%M:%S")}

    def time_between(self, start: str, end: str) -> Dict:
        delta = self._parse(end) - self._parse(start)
        return {
            "total_seconds": delta.total_seconds(),
            "days": delta.days,
            "hours": round(delta.total_seconds() / 3600, 2),
        }

    # -- hashing / encoding ---------------------------------------------------
    def hash_text(self, text: str, algorithm: str = "sha256") -> Dict:
        algorithm = algorithm.lower()
        if algorithm not in hashlib.algorithms_guaranteed:
            return {"success": False, "error": f"Unsupported algorithm '{algorithm}'"}
        digest = hashlib.new(algorithm, text.encode("utf-8")).hexdigest()
        return {"algorithm": algorithm, "hash": digest}

    def encode_base64(self, text: str) -> Dict:
        return {"encoded": base64.b64encode(text.encode("utf-8")).decode("ascii")}

    def decode_base64(self, encoded: str) -> Dict:
        try:
            return {"decoded": base64.b64decode(encoded).decode("utf-8")}
        except Exception as e:
            return {"success": False, "error": f"Invalid base64 input: {e}"}

    # -- random / generation --------------------------------------------------
    def generate_password(self, length: int = 16, symbols: bool = True) -> Dict:
        length = max(4, min(length, 256))
        alphabet = string.ascii_letters + string.digits + (string.punctuation if symbols else "")
        return {"password": "".join(random.SystemRandom().choice(alphabet) for _ in range(length))}

    def generate_uuid(self) -> Dict:
        return {"uuid": str(uuid.uuid4())}

    def roll_dice(self, sides: int = 6, count: int = 1) -> Dict:
        count = max(1, min(count, 100))
        rolls = [random.randint(1, max(2, sides)) for _ in range(count)]
        return {"rolls": rolls, "total": sum(rolls)}

    def flip_coin(self, times: int = 1) -> Dict:
        times = max(1, min(times, 1000))
        results = [random.choice(["heads", "tails"]) for _ in range(times)]
        return {"results": results, "heads": results.count("heads"), "tails": results.count("tails")}

    def random_number(self, min_value: int = 0, max_value: int = 100) -> Dict:
        return {"result": random.randint(min_value, max_value)}

    def register_actions(self) -> None:
        self._actions = {
            "text_stats": self.text_stats,
            "slugify": self.slugify,
            "truncate": self.truncate,
            "change_case": self.change_case,
            "similarity": self.similarity,
            "convert_length": self.convert_length,
            "convert_weight": self.convert_weight,
            "convert_temperature": self.convert_temperature,
            "current_time": self.current_time,
            "add_time": self.add_time,
            "time_between": self.time_between,
            "hash_text": self.hash_text,
            "encode_base64": self.encode_base64,
            "decode_base64": self.decode_base64,
            "generate_password": self.generate_password,
            "generate_uuid": self.generate_uuid,
            "roll_dice": self.roll_dice,
            "flip_coin": self.flip_coin,
            "random_number": self.random_number,
        }
