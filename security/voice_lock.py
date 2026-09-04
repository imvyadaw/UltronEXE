"""
Voice Lock (SECURITY)
=======================
Two independent unlock factors, either usable alone or combined:

    passphrase  - a spoken phrase, checked as TEXT. This module never
                  touches audio for this factor - the existing STT
                  pipeline (auto/Google/Whisper, per the
                  UnknownValueError fix) already turns speech into a
                  string; this module just salted-hashes it (PBKDF2,
                  stdlib `hashlib` only) and compares. Works even with
                  zero optional dependencies installed.
    voiceprint  - who is speaking, not what they said. Optional,
                  needs `resemblyzer`: enrolls a short reference clip
                  per name as a 256-d embedding, then verifies a new
                  clip by cosine similarity. This is the actual
                  biometric factor; passphrase alone only proves
                  someone knows the phrase, not who they are.

verify() accepts either or both and returns success only if every
factor it was given passes - so a caller wanting real two-factor
voice auth passes both spoken_text and audio_path together. Same
fail-closed contract as the rest of this project: nothing configured
means nothing unlocks, not an exception.
"""

import hashlib
import hmac
import json
import os
from typing import Dict, Optional

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    import numpy as np

    _RESEMBLYZER_AVAILABLE = True
except Exception:
    _RESEMBLYZER_AVAILABLE = False

VOICE_DATA_DIR_ENV = "SECURITY_VOICE_DATA_DIR"
DEFAULT_VOICE_DATA_DIR = "data/security/voice"
PASSPHRASE_FILENAME = "passphrase.json"
VOICEPRINTS_FILENAME = "voiceprints.pkl"
PBKDF2_ITERATIONS = 200_000
DEFAULT_VOICEPRINT_THRESHOLD = 0.75  # cosine similarity, resemblyzer's own ballpark


class VoiceLock:
    """Passphrase + optional voiceprint verification. Use get_voice_lock()."""

    def __init__(self):
        self._encoder = None  # lazily built, resemblyzer model load is not free

    def is_available(self) -> bool:
        return True  # passphrase factor works with stdlib alone

    def voiceprint_available(self) -> bool:
        return _RESEMBLYZER_AVAILABLE

    def _data_dir(self) -> str:
        path = os.environ.get(VOICE_DATA_DIR_ENV, DEFAULT_VOICE_DATA_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    # ---- passphrase factor -------------------------------------------------

    def _passphrase_path(self) -> str:
        return os.path.join(self._data_dir(), PASSPHRASE_FILENAME)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().lower().split())

    def set_passphrase(self, phrase: str) -> Dict:
        """Salts and hashes `phrase` (PBKDF2-HMAC-SHA256) and stores
        it, replacing any previous passphrase. Returns
        {"success": bool, "error": Optional[str]}."""
        if not phrase or not phrase.strip():
            return {"success": False, "error": "phrase required"}
        salt = os.urandom(16)
        normalized = self._normalize(phrase)
        digest = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        try:
            with open(self._passphrase_path(), "w") as fh:
                json.dump({"salt": salt.hex(), "digest": digest.hex()}, fh)
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def has_passphrase(self) -> bool:
        return os.path.exists(self._passphrase_path())

    def verify_passphrase(self, spoken_text: str) -> Dict:
        """Compares `spoken_text` (already transcribed by the STT
        pipeline) against the stored passphrase, constant-time.
        Returns {"success": bool, "error": Optional[str]}."""
        if not self.has_passphrase():
            return {"success": False, "error": "no passphrase set"}
        if not spoken_text:
            return {"success": False, "error": "spoken_text required"}
        try:
            with open(self._passphrase_path()) as fh:
                stored = json.load(fh)
            salt = bytes.fromhex(stored["salt"])
            normalized = self._normalize(spoken_text)
            digest = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, PBKDF2_ITERATIONS)
            if hmac.compare_digest(digest.hex(), stored["digest"]):
                return {"success": True, "error": None}
            return {"success": False, "error": "passphrase mismatch"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ---- voiceprint factor --------------------------------------------------

    def _voiceprints_path(self) -> str:
        return os.path.join(self._data_dir(), VOICEPRINTS_FILENAME)

    def _get_encoder(self):
        if self._encoder is None:
            self._encoder = VoiceEncoder()
        return self._encoder

    def _embed(self, audio_path: str):
        wav = preprocess_wav(audio_path)
        return self._get_encoder().embed_utterance(wav)

    def enroll_voice(self, name: str, audio_path: str) -> Dict:
        """Embeds `audio_path` (a few seconds of clean speech) and
        stores it as `name`'s voiceprint, overwriting any prior one
        for that name. Returns {"success": bool, "error": Optional[str]}."""
        if not self.voiceprint_available():
            return {"success": False, "error": "resemblyzer not available"}
        if not name or not audio_path:
            return {"success": False, "error": "name and audio_path both required"}
        try:
            import pickle

            embedding = self._embed(audio_path)
            voiceprints = {}
            path = self._voiceprints_path()
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    voiceprints = pickle.load(fh)
            voiceprints[name] = embedding
            with open(path, "wb") as fh:
                pickle.dump(voiceprints, fh)
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def verify_voice(self, audio_path: str, threshold: float = DEFAULT_VOICEPRINT_THRESHOLD) -> Dict:
        """Embeds `audio_path` and compares it by cosine similarity
        against every enrolled voiceprint. Returns
        {"success": bool, "match": Optional[str], "confidence": float,
        "error": Optional[str]}."""
        if not self.voiceprint_available():
            return {"success": False, "match": None, "confidence": 0.0, "error": "resemblyzer not available"}
        path = self._voiceprints_path()
        if not os.path.exists(path):
            return {"success": False, "match": None, "confidence": 0.0, "error": "no voiceprints enrolled"}
        try:
            import pickle

            with open(path, "rb") as fh:
                voiceprints = pickle.load(fh)
            probe = self._embed(audio_path)

            best_name, best_similarity = None, -1.0
            for name, embedding in voiceprints.items():
                similarity = float(np.dot(probe, embedding) / (np.linalg.norm(probe) * np.linalg.norm(embedding)))
                if similarity > best_similarity:
                    best_name, best_similarity = name, similarity

            if best_similarity >= threshold:
                return {"success": True, "match": best_name, "confidence": best_similarity, "error": None}
            return {
                "success": False,
                "match": None,
                "confidence": max(0.0, best_similarity),
                "error": "no match within threshold",
            }
        except Exception as exc:
            return {"success": False, "match": None, "confidence": 0.0, "error": str(exc)}

    # ---- combined ------------------------------------------------------------

    def verify(self, spoken_text: Optional[str] = None, audio_path: Optional[str] = None) -> Dict:
        """Runs whichever factor(s) it's given and succeeds only if
        ALL of them pass. Passing neither is an error, not an
        auto-pass. Returns {"success": bool, "match": Optional[str],
        "error": Optional[str]}."""
        if not spoken_text and not audio_path:
            return {"success": False, "match": None, "error": "at least one of spoken_text or audio_path required"}

        match = None
        if spoken_text:
            result = self.verify_passphrase(spoken_text)
            if not result["success"]:
                return {"success": False, "match": None, "error": result["error"]}
        if audio_path:
            result = self.verify_voice(audio_path)
            if not result["success"]:
                return {"success": False, "match": None, "error": result["error"]}
            match = result["match"]

        return {"success": True, "match": match, "error": None}


_voice_lock: Optional[VoiceLock] = None


def get_voice_lock() -> VoiceLock:
    global _voice_lock
    if _voice_lock is None:
        _voice_lock = VoiceLock()
    return _voice_lock
