"""
Speaker diarization
======================
"Who said that" across a stream of utterances - segments a sequence of
sr.AudioData clips (e.g. successive full_duplex_engine.py turns, or a
recorded meeting split by silence) into speaker turns.

No bundled diarization model (pyannote.audio etc.), consistent with
voice/speaker_recognition.py's own "no trained embedding model" stance,
so this reuses that module's lightweight numpy voiceprint features
directly rather than duplicating feature extraction - diarization here
is just online clustering of the same feature vectors
speaker_recognition.py already extracts for enrollment/identification:

    1. extract a feature vector per utterance (voice/speaker_recognition's
       _extract_features)
    2. compare it by cosine similarity against known clusters seen so far
       in this session
    3. same cluster if similarity clears MATCH_THRESHOLD, otherwise a new
       speaker label (Speaker 1, Speaker 2, ...)
    4. if the voice matches an *enrolled* profile (identify_speaker), use
       that name instead of a generic label

This is a running, in-memory session diarizer - it does not persist
clusters across restarts (voice/speaker_recognition.py's enrolled
profiles already cover the "remember this specific person" case;
this module is purely about telling turns apart within one session).
"""

from typing import Dict, List, Optional

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from voice.speaker_recognition import _extract_features, get_speaker_recognizer
from core.logger import get_logger

logger = get_logger("ultron.interaction.diarization")

MATCH_THRESHOLD = 0.80  # slightly looser than speaker_recognition's own
# enrollment threshold - session clustering only
# needs to tell voices apart, not authenticate


def _cosine_sim(a: "np.ndarray", b: "np.ndarray") -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


class SpeakerDiarizer:
    """One instance per session/conversation - holds the running set of
    speaker clusters seen so far. Not shared across independent
    conversations, since "Speaker 1" in one session has no relation to
    "Speaker 1" in another."""

    def __init__(self):
        self._clusters: List[Dict] = []  # [{"label": str, "centroid": np.ndarray, "count": int}]

    def add_utterance(self, audio) -> Dict:
        """Diarize one utterance's audio, returning {"label", "is_new",
        "enrolled_name"} - `enrolled_name` is set only if the voice
        matches a profile from voice/speaker_recognition.py's enrollment
        store, and takes priority over a generic cluster label."""
        if not HAS_NUMPY:
            return {"error": "numpy not installed - diarization requires it"}

        try:
            features = _extract_features(audio)
        except Exception as e:
            return {"error": f"Feature extraction failed: {e}"}

        enrolled_name: Optional[str] = None
        try:
            match = get_speaker_recognizer().identify(audio)
            if isinstance(match, dict) and match.get("name"):
                enrolled_name = match["name"]
        except Exception as e:
            logger.debug(f"Enrolled-speaker lookup skipped: {e}")

        best_idx, best_sim = None, -1.0
        for i, cluster in enumerate(self._clusters):
            sim = _cosine_sim(features, cluster["centroid"])
            if sim > best_sim:
                best_idx, best_sim = i, sim

        if best_idx is not None and best_sim >= MATCH_THRESHOLD:
            cluster = self._clusters[best_idx]
            n = cluster["count"]
            cluster["centroid"] = (cluster["centroid"] * n + features) / (n + 1)
            cluster["count"] += 1
            if enrolled_name:
                cluster["label"] = enrolled_name
            return {
                "label": cluster["label"],
                "is_new": False,
                "similarity": round(best_sim, 3),
                "enrolled_name": enrolled_name,
            }

        label = enrolled_name or f"Speaker {len(self._clusters) + 1}"
        self._clusters.append({"label": label, "centroid": features, "count": 1})
        return {
            "label": label,
            "is_new": True,
            "similarity": round(best_sim, 3) if best_idx is not None else None,
            "enrolled_name": enrolled_name,
        }

    def speakers_seen(self) -> List[str]:
        return [c["label"] for c in self._clusters]

    def reset(self) -> None:
        self._clusters.clear()


def get_diarizer() -> SpeakerDiarizer:
    """New diarizer per call - callers that want a persistent session
    diarizer should hold onto the instance themselves (e.g.
    full_duplex_engine.py keeping one for the lifetime of a
    conversation), same "don't force a global singleton on stateful
    per-session objects" pattern as agent_communication.py's per-swarm
    bus vs. get_agent_bus()'s module-level default."""
    return SpeakerDiarizer()
