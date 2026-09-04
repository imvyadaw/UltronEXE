"""
Security agent
==============
Local security helpers: password strength checks, secure password
generation, file-permission auditing, and a thin pass-through to
core/permissions.py so destructive-tool gating has an agent-shaped
entry point alongside the others in agents/.
"""

import math
import os
import re
import secrets
import string
from pathlib import Path
from typing import Dict

from core.permissions import PermissionGate
from agents.base_agent import BaseAgent

_COMMON_PASSWORDS = {
    "password",
    "123456",
    "123456789",
    "qwerty",
    "abc123",
    "letmein",
    "111111",
    "iloveyou",
    "admin",
    "welcome",
    "monkey",
    "password1",
}


class SecurityAgent(BaseAgent):
    """Password hygiene, file-permission audits, and confirmation gating."""

    capabilities = ["security", "password", "permissions", "secrets"]

    def __init__(self):
        super().__init__("security", "Password hygiene, file-permission audits, confirmation gating")
        self._gate = PermissionGate()

    def requires_confirmation(self, tool_name: str) -> Dict:
        """Whether `tool_name` is on the destructive-action list and
        should be confirmed with the user before running."""
        return {"tool_name": tool_name, "requires_confirmation": self._gate.requires_confirmation(tool_name)}

    def check_password_strength(self, password: str) -> Dict:
        """Heuristic password strength score (0-100) with reasons."""
        if not password:
            return {"error": "No password provided"}

        length = len(password)
        classes = sum(
            [
                bool(re.search(r"[a-z]", password)),
                bool(re.search(r"[A-Z]", password)),
                bool(re.search(r"[0-9]", password)),
                bool(re.search(r"[^a-zA-Z0-9]", password)),
            ]
        )
        # Estimate entropy from character-class pool size actually used.
        pool_size = 0
        if re.search(r"[a-z]", password):
            pool_size += 26
        if re.search(r"[A-Z]", password):
            pool_size += 26
        if re.search(r"[0-9]", password):
            pool_size += 10
        if re.search(r"[^a-zA-Z0-9]", password):
            pool_size += 32
        entropy = length * math.log2(pool_size) if pool_size else 0

        issues = []
        if length < 8:
            issues.append("Shorter than 8 characters")
        if classes < 3:
            issues.append("Uses fewer than 3 character classes (lower/upper/digit/symbol)")
        if password.lower() in _COMMON_PASSWORDS:
            issues.append("This is one of the most commonly breached passwords")
        if re.search(r"(.)\1\1", password):
            issues.append("Contains a repeated-character run")

        score = max(0, min(100, round(entropy / 0.6)))
        if issues:
            score = min(score, 40)

        if score >= 80:
            rating = "strong"
        elif score >= 50:
            rating = "moderate"
        else:
            rating = "weak"

        return {"score": score, "rating": rating, "entropy_bits": round(entropy, 1), "issues": issues}

    def generate_secure_password(self, length: int = 16, symbols: bool = True) -> Dict:
        """Generate a cryptographically random password."""
        if length < 8:
            return {"error": "length must be at least 8"}
        alphabet = string.ascii_letters + string.digits
        if symbols:
            alphabet += "!@#$%^&*()-_=+"
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        return {"password": password, "length": length}

    def audit_file_permissions(self, path: str) -> Dict:
        """Report whether a file/folder is world-writable or unusually
        permissive - a quick local security smell-test, not a full audit."""
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        try:
            mode = oct(os.stat(p).st_mode)[-3:]
            world_writable = mode[-1] in ("2", "3", "6", "7")
            return {
                "path": str(p),
                "mode": mode,
                "world_writable": world_writable,
                "warning": "World-writable - consider tightening permissions" if world_writable else None,
            }
        except Exception as e:
            return {"error": str(e)}

    def scan_env_for_secrets(self, path: str) -> Dict:
        """Best-effort scan of a text file for likely leaked secrets
        (API keys, tokens) so a user doesn't accidentally commit them."""
        p = Path(path).expanduser()
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        patterns = {
            "generic_api_key": r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
            "aws_key": r"AKIA[0-9A-Z]{16}",
            "private_key_block": r"-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----",
        }
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {"error": str(e)}

        findings = []
        for name, pattern in patterns.items():
            if re.search(pattern, text):
                findings.append(name)
        return {"path": str(p), "possible_secrets_found": findings, "clean": len(findings) == 0}
