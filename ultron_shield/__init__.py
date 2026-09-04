"""
ULTRON_SHIELD
=============
Defensive security layer for ULTRON itself: is this really you at the
keyboard, is something probing the host or companion API, where are
secrets actually kept, what sensitive data should never hit a log
line, what should code run under when we're not sure it's safe, and
is there a tamper-evident record of all of it afterward.

Every module here is protective, not offensive - nothing in this
package scans, attacks, or probes anything other than ULTRON's own
processes and logs. Detection thresholds are conservative by design:
a false "huh, that's odd" prompting a re-auth is a much cheaper
mistake than a missed intrusion, but this package always leaves the
final call (lock, alert, ignore) to a callback you register, never a
hardcoded automatic action against the outside world.
"""

from .behavior_biometrics import BehaviorBiometrics, TypingSample, ProfileMismatch
from .intrusion_detector import IntrusionDetector, IntrusionEvent, Severity as IntrusionSeverity
from .secure_enclave import SecureEnclave
from .privacy_filter import PrivacyFilter, RedactionRule
from .sandbox_executor import SandboxExecutor, ExecutionResult, Policy
from .audit_logger import AuditLogger, AuditEntry

__all__ = [
    "BehaviorBiometrics",
    "TypingSample",
    "ProfileMismatch",
    "IntrusionDetector",
    "IntrusionEvent",
    "IntrusionSeverity",
    "SecureEnclave",
    "PrivacyFilter",
    "RedactionRule",
    "SandboxExecutor",
    "ExecutionResult",
    "Policy",
    "AuditLogger",
    "AuditEntry",
]
