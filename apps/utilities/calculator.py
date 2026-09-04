"""Windows Calculator automation. compute() evaluates the expression
directly in Python (a safe restricted eval) rather than driving the
calculator UI button-by-button, which is both faster and more reliable;
open() still launches the visible app for the user to see."""

import math
from typing import Dict

from apps.base_app import BaseApp

_SAFE_NAMES = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
_SAFE_NAMES.update({"abs": abs, "round": round, "pow": pow})


class CalculatorApp(BaseApp):
    """Open the Calculator app and evaluate arithmetic expressions."""

    APP_NAME = "calculator"
    PROCESS_NAMES = ["calculator.exe", "calc.exe"]
    EXE_HINTS = ["calc", "calc.exe"]

    def compute(self, expression: str) -> Dict:
        try:
            allowed_chars = set("0123456789+-*/().,% ")
            if not all(c.isalnum() or c in allowed_chars or c == "_" for c in expression):
                return {"error": "Expression contains disallowed characters"}
            result = eval(expression, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307 - restricted namespace
            return {"success": True, "expression": expression, "result": result}
        except Exception as e:
            return {"error": str(e)}
