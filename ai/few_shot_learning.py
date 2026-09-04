"""
Few-shot learning
=================
Stores (task_type, input, output) examples in SQLite and builds
few-shot prompts from them - a lightweight way for Ultron to "learn"
a user's preferred style for a recurring task (e.g. how they like
emails drafted, or how verbose they want code explanations) without
any model fine-tuning: just prepend their best past examples to the
next prompt.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "few_shot_examples.db"


class FewShotLearner:
    """Store and retrieve labeled examples to steer future prompts."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                input_text TEXT,
                output_text TEXT,
                rating INTEGER DEFAULT 1,
                created_at REAL
            )""")
        self._conn.commit()

    def add_example(self, task_type: str, input_text: str, output_text: str, rating: int = 1) -> Dict:
        """Save an example. `rating` lets good/approved outputs (e.g. the
        user said "yes, like that") outrank ordinary ones when selecting
        which examples to show the model later."""
        try:
            self._conn.execute(
                "INSERT INTO examples (task_type, input_text, output_text, rating, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_type, input_text, output_text, rating, time.time()),
            )
            self._conn.commit()
            return {"success": True, "task_type": task_type}
        except Exception as e:
            return {"error": str(e)}

    def get_examples(self, task_type: str, k: int = 3) -> Dict:
        """Best `k` examples for `task_type`, highest-rated and most recent first."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT input_text, output_text, rating FROM examples WHERE task_type = ? "
                "ORDER BY rating DESC, created_at DESC LIMIT ?",
                (task_type, k),
            )
            rows = cur.fetchall()
            examples = [{"input": r[0], "output": r[1], "rating": r[2]} for r in rows]
            return {"task_type": task_type, "count": len(examples), "examples": examples}
        except Exception as e:
            return {"error": str(e)}

    def build_prompt(self, task_type: str, new_input: str, k: int = 3, instructions: str = "") -> Dict:
        """Compose a few-shot prompt: optional instructions, then up to
        `k` past examples, then the new input to complete."""
        result = self.get_examples(task_type, k)
        if "error" in result:
            return result

        parts: List[str] = []
        if instructions:
            parts.append(instructions.strip())
        for ex in result["examples"]:
            parts.append(f"Input: {ex['input']}\nOutput: {ex['output']}")
        parts.append(f"Input: {new_input}\nOutput:")

        return {"task_type": task_type, "prompt": "\n\n".join(parts), "examples_used": result["count"]}

    def rate_example_by_input(self, task_type: str, input_text: str, rating: int) -> Dict:
        """Bump/lower the rating of the most recent example matching
        `input_text` - e.g. after the user approves or rejects an output."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id FROM examples WHERE task_type = ? AND input_text = ? ORDER BY created_at DESC LIMIT 1",
                (task_type, input_text),
            )
            row = cur.fetchone()
            if not row:
                return {"error": "No matching example found"}
            cur.execute("UPDATE examples SET rating = ? WHERE id = ?", (rating, row[0]))
            self._conn.commit()
            return {"success": True, "id": row[0], "rating": rating}
        except Exception as e:
            return {"error": str(e)}
