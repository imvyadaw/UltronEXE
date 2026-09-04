"""
Swarm security agent
=====================
Specialist wrapper around agents/security_agent.py's SecurityAgent
(unchanged - password strength/generation, file-permission audits,
secret scanning, confirmation gating). This is the agent
consensus_engine.py leans on for cross-checking anything another
specialist proposes that touches credentials, permissions, or a
destructive action - e.g. agent_orchestrator.run_swarm_review() can
send a code_agent-authored script here before treating it as safe to
run, the same "second opinion before acting" pattern
core/permissions.py's PermissionGate already applies to destructive
tool calls one layer down.
"""

import re
from typing import Dict, List

from agents.security_agent import SecurityAgent
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent

#: task["action"] -> SecurityAgent method name + which task key(s) feed it.
#: "review" isn't here - it's handled by _review_snippet() below, since
#: SecurityAgent has no method that takes raw text rather than a file path.
_ACTIONS = {
    "check_password": ("check_password_strength", ("password",)),
    "generate_password": ("generate_secure_password", ("length", "symbols")),
    "audit_permissions": ("audit_file_permissions", ("path",)),
    "scan_secrets": ("scan_env_for_secrets", ("path",)),
}

#: Pattern -> what it flags, for _review_snippet()'s text-based scan.
#: Deliberately non-LLM, same heuristic-regex style as
#: agents/security_agent.py's own scan_env_for_secrets()/check_password_strength()
#: - a static pattern scan, not a semantic code review (code_agent.py's
#: review_code() covers that side; the two are meant to be cross-checked
#: together via agent_orchestrator.run_swarm_review(), not to duplicate
#: each other).
_RISK_PATTERNS = {
    r"os\.system\(": "Calls os.system() - runs an arbitrary shell command",
    r"subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True": "subprocess call with shell=True - shell injection risk",
    r"\beval\(": "Uses eval() - arbitrary code execution risk",
    r"\bexec\(": "Uses exec() - arbitrary code execution risk",
    r"pickle\.loads?\(": "Uses pickle - insecure deserialization risk on untrusted input",
    r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}": "Looks like a hardcoded API key/secret/token",
    r"AKIA[0-9A-Z]{16}": "Looks like a hardcoded AWS access key",
    r"-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----": "Contains an embedded private key",
}


class SwarmSecurityAgent(BaseSpecialistAgent):
    """Password hygiene, permission audits, and secret scanning, from the swarm."""

    capabilities = ["security", "password", "permissions", "secrets", "audit"]
    keywords = [
        "password",
        "secure",
        "security",
        "vulnerable",
        "vulnerability",
        "permission",
        "secret",
        "credential",
        "encrypt",
        "audit",
        "exploit",
        "risk",
    ]

    def __init__(self):
        super().__init__("security", "Password hygiene, permission audits, secret scanning, snippet review")
        self._backend = SecurityAgent()

    def _run(self, task: Dict) -> Dict:
        action = (task.get("action") or "check_password").lower()

        if action == "review":
            text = task.get("description") or task.get("code") or task.get("text")
            if not text:
                return {"error": "No description/code/text provided for review"}
            return self._review_snippet(text)

        if action not in _ACTIONS:
            return {"error": f"Unknown security action '{action}' - use one of {list(_ACTIONS) + ['review']}"}

        method_name, arg_keys = _ACTIONS[action]
        method = getattr(self._backend, method_name)

        if action == "check_password":
            password = task.get("password") or task.get("description")
            if not password:
                return {"error": "No password provided for check_password"}
            return method(password)
        if action == "generate_password":
            return method(length=task.get("length", 16), symbols=task.get("symbols", True))

        path = task.get("path") or task.get("description")
        if not path:
            return {"error": f"No path provided for {action}"}
        return method(path)

    def _review_snippet(self, text: str) -> Dict:
        """Static pattern scan of arbitrary text/code (not a file on disk -
        see _RISK_PATTERNS above for why this can't just call
        SecurityAgent.scan_env_for_secrets(), which expects a path).
        Returns a "vote" key ("unsafe"/"safe") alongside "risk" and
        "findings" so consensus_engine.py's majority/unanimous strategies
        can weigh this against another specialist's explicit vote, not
        just its free-text result."""
        findings: List[str] = []
        for pattern, explanation in _RISK_PATTERNS.items():
            if re.search(pattern, text):
                findings.append(explanation)

        if not findings:
            risk = "low"
        elif len(findings) == 1:
            risk = "medium"
        else:
            risk = "high"

        return {
            "risk": risk,
            "findings": findings,
            "vote": "safe" if risk == "low" else "unsafe",
        }
