"""
Improvement engine
===================
Turns code_analyzer.py's raw analysis into a bounded, prioritized list
of improvement targets patch_generator.py can act on.

This used to only surface syntax errors, on the reasoning that they
were the one category with an objective pass/fail signal afterwards.
code_analyzer.py now does real static analysis - cyclomatic
complexity, oversized functions, too many parameters, deep nesting,
mutable default arguments, bare/swallowed excepts, eval()/exec() on
dynamic input, identity-compare-on-literal bugs, wildcard/unused
imports, duplicate (dead) definitions, hidden global/nonlocal state,
and TODO markers/long lines. All of it is still guarded by the exact
same objective gate downstream: evolution_manager.py only ever accepts
a run if the sandbox compiles AND its test suite passes after the
patches land. That gate is what makes it safe to act on "fuzzier"
issues now - it hasn't gotten any looser.

Syntax errors are always included in full, since the sandbox can't
even compile until every one of those is fixed. Everything else is
ranked by severity (critical > high > medium > low > info) and capped
at `max_issues` per call purely so one evaluate() run doesn't try to
fire dozens of single-file LLM patch requests at once - no `type` is
filtered out, every category code_analyzer.py can produce is eligible.
"""

import re
from typing import Dict, List, Optional

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class ImprovementEngine:
    """Prioritizes CodeAnalyzer findings into patch_generator-ready issues."""

    def identify(self, analysis: Dict, max_issues: int = 25, min_severity: str = "info") -> List[Dict]:
        """analysis: whatever CodeAnalyzer.analyze() returned.

        Args:
            max_issues: total cap on returned issues (syntax errors
                always fit inside this budget first, uncapped among
                themselves - the sandbox needs every one fixed).
            min_severity: drop findings weaker than this
                ("critical"/"high"/"medium"/"low"/"info"); default
                keeps everything so callers who want the full picture
                (e.g. summarize()) still see it.

        Returns:
            A list of {"file", "type", "description", "severity",
            "line"} dicts, patch_generator.py-ready, syntax fixes
            first, then the remaining findings sorted by severity.
        """
        issues: List[Dict] = [
            {
                "file": x["file"],
                "type": "syntax_fix",
                "description": x.get("error", "syntax error"),
                "severity": "critical",
                "line": self._line_from_syntax_error(x.get("error", "")),
            }
            for x in analysis.get("syntax_errors", [])
        ]

        min_rank = _SEVERITY_ORDER.get(min_severity, len(_SEVERITY_ORDER) - 1)
        findings = [
            f for f in analysis.get("issues", []) if _SEVERITY_ORDER.get(f.get("severity", "info"), 4) <= min_rank
        ]
        findings.sort(
            key=lambda f: (
                _SEVERITY_ORDER.get(f.get("severity", "info"), 4),
                f.get("file", ""),
                f.get("line") or 0,
            )
        )

        budget = max(0, max_issues - len(issues))
        for f in findings[:budget]:
            issues.append(
                {
                    "file": f["file"],
                    "type": f.get("type", "improvement"),
                    "description": f.get("message", "improvement"),
                    "severity": f.get("severity", "info"),
                    "line": f.get("line"),
                }
            )

        return issues

    def summarize(self, analysis: Dict) -> Dict:
        """Human-readable rollup for logs/dashboards - independent of
        identify()'s capped patch queue, so it always reflects the
        full scan (how many files, how bad, which issue types dominate)."""
        stats = analysis.get("stats", {})
        by_type = stats.get("by_type", {})
        top_types = sorted(by_type.items(), key=lambda kv: -kv[1])[:5]
        return {
            "files_scanned": analysis.get("files", 0),
            "syntax_errors": len(analysis.get("syntax_errors", [])),
            "total_issues": stats.get("issue_count", 0),
            "by_severity": stats.get("by_severity", {}),
            "avg_complexity": stats.get("avg_complexity", 0.0),
            "top_issue_types": top_types,
        }

    @staticmethod
    def _line_from_syntax_error(error: str) -> Optional[int]:
        """SyntaxError's str() usually ends with '(file, line N)' - best-
        effort extraction so syntax issues carry a line number too, same
        as every other finding. Returns None if it can't be parsed;
        callers already treat a missing line as harmless."""
        match = re.search(r"line (\d+)", error)
        return int(match.group(1)) if match else None
