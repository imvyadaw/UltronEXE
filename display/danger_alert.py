"""
Danger Alert
============
The delivery layer for EYES/threat_sense.py findings, same relationship
reports.py already has to MEMORY/'s raw data: threat_sense.py answers
"what was flagged", this module answers "how should Ultron say that
out loud" - phrased through CORE.personality.speak() so an alert reads
in Ultron's current voice rather than a bare dict, with the same
plain-summary fallback reports.py uses if personality/tone_manager has
no matching phrase category.

raise_alert() is the one place in this phase that calls
screen_popup.show() automatically rather than leaving it to a caller -
deliberately, since "flag a hazard" and "tell the user" are the same
action for this module's one job, unlike price_tag.py/face_label.py
where drawing and deciding are kept separate. It still never *acts*
beyond speaking + popping up a notification (no calling emergency
services, no locking doors) - this module has exactly the same reach
MEMORY/forget.py claims for itself: additive, and it can't escalate
past its own boundary.
"""

from typing import Dict, List, Optional


class DangerAlert:
    """Turns threat_sense findings into spoken + on-screen alerts. Use get_danger_alert()."""

    def check_and_alert(self, frame, previous_frame=None, notify: bool = True) -> List[Dict]:
        """Runs threat_sense.assess() and raises an alert for every
        finding. Returns the raw findings list (possibly empty)
        regardless of whether notify succeeded, so a caller can log or
        inspect what was found even in a headless environment."""
        findings = self._assess(frame, previous_frame)
        for finding in findings:
            self.raise_alert(finding, notify=notify)
        return findings

    def raise_alert(self, finding: Dict, notify: bool = True) -> str:
        """Phrases one finding and, if notify, pops it up on screen.
        Returns the phrased text either way."""
        text = self._speak(finding)
        if notify:
            try:
                from display.screen_popup import get_screen_popup

                get_screen_popup().show(text, title="Ultron - heads up")
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("display.danger_alert.raise_alert")
        return text

    @staticmethod
    def _assess(frame, previous_frame) -> List[Dict]:
        try:
            from eyes.threat_sense import get_threat_sense

            return get_threat_sense().assess(frame, previous_frame=previous_frame)
        except Exception:
            return []

    @staticmethod
    def _speak(finding: Dict) -> str:
        kind = finding.get("kind", "something")
        level = finding.get("level", "low")
        plain = {
            "motion_spike": "I noticed sudden movement.",
            "fire_signal": "I'm seeing something that looks like it could be fire - worth checking.",
            "unrecognized_person": "There's someone in view I don't recognize.",
        }.get(kind, f"I flagged a {level}-priority {kind}.")

        try:
            from core.personality import get_personality

            phrase = get_personality().speak("general_update", message=plain)
            return phrase.get("text") or plain
        except Exception:
            return plain


_danger_alert: Optional[DangerAlert] = None


def get_danger_alert() -> DangerAlert:
    global _danger_alert
    if _danger_alert is None:
        _danger_alert = DangerAlert()
    return _danger_alert
