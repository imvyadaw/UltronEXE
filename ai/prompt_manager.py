"""Prompt manager
==============
Lightweight prompt optimization on top of ai/prompts/ (TemplateRegistry +
PromptTemplate): lets a caller register two or more phrasings of the same
task prompt as "variants", records whether each render led to a usable
result, and reports which variant is winning - so Ultron's prompts can
improve empirically instead of by guesswork.

This is intentionally simple (in-memory counters, persisted to SQLite so
stats survive a restart) rather than a full experiment-tracking system -
Ultron is a single-user assistant, not a service running thousands of
prompt calls a day.

Usage:
    from ai.prompt_manager import get_prompt_manager

    pm = get_prompt_manager()
    pm.register_variant("summarize", "short", "Summarize in one sentence: {text}")
    pm.register_variant("summarize", "detailed", "Summarize, covering all key points: {text}")

    variant_id, prompt_text = pm.get_best_variant("summarize", text="...")
    # ... call the model with prompt_text ...
    pm.record_result("summarize", variant_id, success=True)
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai.prompts.templates import PromptTemplate, TemplateRegistry

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "prompt_stats.db"


class PromptManager:
    """Registers prompt variants per task and tracks which one performs best."""

    def __init__(self):
        self._registry = TemplateRegistry()
        # task_name -> {variant_id: PromptTemplate}
        self._variants: Dict[str, Dict[str, PromptTemplate]] = {}

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS prompt_stats (
                task TEXT,
                variant TEXT,
                uses INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                updated_at REAL,
                PRIMARY KEY (task, variant)
            )""")
        self._conn.commit()

    # -- registration ---------------------------------------------------------
    def register_variant(self, task: str, variant_id: str, template: str, description: str = "") -> None:
        """Add a phrasing variant for `task`, identified by `variant_id`."""
        tpl = PromptTemplate(name=f"{task}:{variant_id}", template=template, description=description)
        self._variants.setdefault(task, {})[variant_id] = tpl
        self._registry.register(tpl)
        self._conn.execute(
            "INSERT OR IGNORE INTO prompt_stats (task, variant, uses, successes, updated_at) VALUES (?, ?, 0, 0, ?)",
            (task, variant_id, time.time()),
        )
        self._conn.commit()

    def variants_for(self, task: str) -> List[str]:
        return list(self._variants.get(task, {}).keys())

    # -- selection --------------------------------------------------------------
    def _success_rate(self, task: str, variant: str) -> float:
        cur = self._conn.cursor()
        cur.execute("SELECT uses, successes FROM prompt_stats WHERE task=? AND variant=?", (task, variant))
        row = cur.fetchone()
        if not row or row[0] == 0:
            return 0.5  # neutral prior for an untried variant - gives it a fair shot
        uses, successes = row
        return successes / uses

    def best_variant_id(self, task: str) -> Optional[str]:
        """The variant with the highest observed success rate for `task`,
        or None if no variants are registered."""
        variants = self.variants_for(task)
        if not variants:
            return None
        return max(variants, key=lambda v: self._success_rate(task, v))

    def get_best_variant(self, task: str, **kwargs) -> Tuple[str, str]:
        """Render the current best-performing variant for `task` with the
        given placeholder values. Returns (variant_id, rendered_prompt).
        Raises KeyError if no variants are registered for this task."""
        variant_id = self.best_variant_id(task)
        if variant_id is None:
            raise KeyError(f"No prompt variants registered for task '{task}'")
        tpl = self._variants[task][variant_id]
        return variant_id, tpl.render(**kwargs)

    # -- feedback ---------------------------------------------------------------
    def record_result(self, task: str, variant_id: str, success: bool) -> None:
        """Record whether a call using this variant succeeded (produced a
        usable result) or not, so future get_best_variant() calls can
        favor what's actually working."""
        self._conn.execute(
            """UPDATE prompt_stats SET uses = uses + 1, successes = successes + ?, updated_at = ?
               WHERE task = ? AND variant = ?""",
            (1 if success else 0, time.time(), task, variant_id),
        )
        self._conn.commit()

    def stats(self, task: str) -> Dict[str, Dict]:
        """Raw usage/success stats for every variant of `task`, for a
        dashboard or debugging."""
        cur = self._conn.cursor()
        cur.execute("SELECT variant, uses, successes FROM prompt_stats WHERE task=?", (task,))
        return {
            variant: {"uses": uses, "successes": successes, "success_rate": (successes / uses) if uses else None}
            for variant, uses, successes in cur.fetchall()
        }


_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    global _manager
    if _manager is None:
        _manager = PromptManager()
    return _manager
