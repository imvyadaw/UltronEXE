"""
Consensus engine
==================
When agent_orchestrator.py sends the *same* question to several
specialists instead of splitting work across them - e.g. "review this
script for problems" going to both code_agent.py and security_agent.py
- something has to turn N separate {"result": ...}/{"error": ...} dicts
into one answer. That's this file's only job. It never calls an
agent itself; it consumes whatever agent_orchestrator.run_swarm_review()
already collected.

Three strategies, picked per call:

    majority   - categorical votes (task["vote"] present on each
                 result): the most common vote wins, ties reported as
                 ties rather than arbitrarily broken.
    unanimous  - like majority, but only "reaches" consensus if every
                 non-erroring agent agrees; otherwise flags dissent
                 rather than picking a winner. Use for anything where a
                 single holdout matters (e.g. security sign-off).
    weighted   - no discrete "vote", just each agent's own
                 result["confidence"] (0-1, if the agent supplied one;
                 defaults to 1.0) used to weight which result is
                 reported as primary - not a numeric average, since
                 results are free-text/dicts, not numbers.
"""

from collections import Counter
from typing import Dict, Optional


class ConsensusEngine:
    """Combines several agents' results on the same question into one answer."""

    def reach_consensus(self, agent_results: Dict[str, Dict], strategy: str = "majority") -> Dict:
        """`agent_results` maps agent name -> that agent's result dict
        (as returned by BaseSpecialistAgent.handle()). Agents whose
        result contains "error" are excluded from voting but listed
        under "excluded" so the caller knows who didn't weigh in."""
        if not agent_results:
            return {"error": "No agent results provided"}

        usable = {name: r for name, r in agent_results.items() if isinstance(r, dict) and "error" not in r}
        excluded = {name: r["error"] for name, r in agent_results.items() if name not in usable}

        if not usable:
            return {"error": "Every agent errored - no consensus possible", "excluded": excluded}

        if strategy == "majority":
            outcome = self._majority(usable)
        elif strategy == "unanimous":
            outcome = self._unanimous(usable)
        elif strategy == "weighted":
            outcome = self._weighted(usable)
        else:
            return {"error": f"Unknown strategy '{strategy}' - use 'majority', 'unanimous', or 'weighted'"}

        outcome["excluded"] = excluded
        outcome["participants"] = sorted(usable.keys())
        return outcome

    def _votes(self, usable: Dict[str, Dict]) -> Dict[str, str]:
        """Each agent's vote, falling back to its raw result text if it
        didn't supply an explicit "vote" key - lets consensus work even
        for free-text answers, just less precisely than an explicit vote."""
        votes = {}
        for name, result in usable.items():
            votes[name] = str(result.get("vote", result.get("result", result)))
        return votes

    def _majority(self, usable: Dict[str, Dict]) -> Dict:
        votes = self._votes(usable)
        counts = Counter(votes.values())
        top_count = max(counts.values())
        winners = [v for v, c in counts.items() if c == top_count]
        return {
            "consensus": winners[0] if len(winners) == 1 else None,
            "tied": winners if len(winners) > 1 else [],
            "vote_counts": dict(counts),
            "agreement_ratio": round(top_count / len(votes), 2),
            "votes": votes,
        }

    def _unanimous(self, usable: Dict[str, Dict]) -> Dict:
        votes = self._votes(usable)
        distinct = set(votes.values())
        unanimous = len(distinct) == 1
        return {
            "consensus": next(iter(distinct)) if unanimous else None,
            "unanimous": unanimous,
            "dissenting": (
                []
                if unanimous
                else [name for name, v in votes.items() if v != Counter(votes.values()).most_common(1)[0][0]]
            ),
            "votes": votes,
        }

    def _weighted(self, usable: Dict[str, Dict]) -> Dict:
        ranked = sorted(
            usable.items(),
            key=lambda kv: kv[1].get("confidence", 1.0),
            reverse=True,
        )
        top_name, top_result = ranked[0]
        return {
            "consensus": top_result.get("result", top_result),
            "primary_agent": top_name,
            "confidence": top_result.get("confidence", 1.0),
            "ranking": [{"agent": name, "confidence": r.get("confidence", 1.0)} for name, r in ranked],
        }


_engine: Optional[ConsensusEngine] = None


def get_consensus_engine() -> ConsensusEngine:
    global _engine
    if _engine is None:
        _engine = ConsensusEngine()
    return _engine
