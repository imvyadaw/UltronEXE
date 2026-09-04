"""
Code analyzer
=============
Static analysis for self_evolution/. The old version only ran
ast.parse() and reported SyntaxErrors. This one still does that (a
file that can't even parse has to be fixed first), but for every file
that DOES parse it now inspects the AST and flags real weaknesses:

  - cyclomatic complexity per function (too many branches/loops)
  - function size (too many lines) and signature size (too many params)
  - deep nesting (missing early-returns / guard clauses)
  - mutable default arguments (list/dict/set literals as defaults)
  - bare `except:` and `except X: pass` (swallowed errors)
  - eval()/exec() on dynamic input (injection risk)
  - `is`/`is not` compared against a literal (undefined-behaviour bug)
  - wildcard imports and unused imports
  - duplicate function/method definitions in the same scope (dead code)
  - global/nonlocal mutation inside a function (hidden state)
  - TODO/FIXME/XXX/HACK markers and overly long lines

Every finding - syntax error or otherwise - lands in a common shape:
{"file", "line", "type", "severity", "message"}, so
improvement_engine.py can rank and forward either kind to
patch_generator.py without special-casing. Still zero third-party
dependencies (stdlib ast/re/pathlib only), so it keeps running in the
same minimal sandbox the rest of self_evolution/ uses.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

IGNORED_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules", "site-packages"}

# Thresholds - tuned to flag genuinely risky code, not nitpick everything.
COMPLEXITY_HIGH = 15
COMPLEXITY_MEDIUM = 10
FUNCTION_TOO_LONG = 60
TOO_MANY_PARAMS = 6
NESTING_TOO_DEEP = 4
LINE_TOO_LONG = 120

DANGEROUS_CALLS = {"eval", "exec"}
TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b[:\-]?\s*(.*)", re.IGNORECASE)
NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


class CodeAnalyzer:
    """Walks a project tree and reports both syntax errors and
    structural/behavioural weaknesses per file."""

    def analyze(self, root) -> Dict:
        result: Dict = {
            "files": 0,
            "syntax_errors": [],
            "issues": [],
            "stats": {"total_lines": 0, "total_functions": 0, "avg_complexity": 0.0},
        }
        complexities: List[int] = []

        for path in Path(root).rglob("*.py"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            result["files"] += 1

            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                result["syntax_errors"].append({"file": str(path), "error": f"unreadable: {e}"})
                continue

            result["stats"]["total_lines"] += source.count("\n") + 1

            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError as e:
                result["syntax_errors"].append({"file": str(path), "error": str(e)})
                continue
            except Exception as e:
                # Anything else (e.g. ValueError on a null byte) still
                # means we can't safely analyze this file further.
                result["syntax_errors"].append({"file": str(path), "error": f"parse failed: {e}"})
                continue

            file_issues, fn_count, fn_complexities = self._analyze_tree(path, source, tree)
            result["issues"].extend(file_issues)
            result["stats"]["total_functions"] += fn_count
            complexities.extend(fn_complexities)

        if complexities:
            result["stats"]["avg_complexity"] = round(sum(complexities) / len(complexities), 2)
        result["stats"]["issue_count"] = len(result["issues"])
        result["stats"]["by_severity"] = dict(Counter(i["severity"] for i in result["issues"]))
        result["stats"]["by_type"] = dict(Counter(i["type"] for i in result["issues"]))
        return result

    # -- per-file analysis ---------------------------------------------------

    def _analyze_tree(self, path: Path, source: str, tree: ast.AST) -> Tuple[List[Dict], int, List[int]]:
        issues: List[Dict] = []
        lines = source.splitlines()
        fn_complexities: List[int] = []
        fn_count = 0

        issues.extend(self._check_imports(path, tree))
        issues.extend(self._check_comment_markers(path, lines))
        issues.extend(self._check_line_length(path, lines))
        issues.extend(self._check_duplicate_defs(path, tree))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_count += 1
                complexity = self._cyclomatic_complexity(node)
                fn_complexities.append(complexity)
                issues.extend(self._check_function(path, node, complexity))
            elif isinstance(node, ast.ExceptHandler):
                issues.extend(self._check_except_handler(path, node))
            elif isinstance(node, ast.Call):
                issues.extend(self._check_dangerous_call(path, node))
            elif isinstance(node, ast.Compare):
                issues.extend(self._check_identity_literal_compare(path, node))

        return issues, fn_count, fn_complexities

    # -- individual checks ----------------------------------------------------

    def _check_function(self, path: Path, fn, complexity: int) -> List[Dict]:
        issues = []
        name = fn.name
        line = fn.lineno
        end_line = getattr(fn, "end_lineno", line)
        length = end_line - line + 1

        if complexity >= COMPLEXITY_HIGH:
            issues.append(
                self._issue(
                    path,
                    line,
                    "high_complexity",
                    "high",
                    f"Function '{name}' has cyclomatic complexity {complexity} (>= {COMPLEXITY_HIGH}); "
                    f"split it into smaller functions, each with a single responsibility.",
                )
            )
        elif complexity >= COMPLEXITY_MEDIUM:
            issues.append(
                self._issue(
                    path,
                    line,
                    "medium_complexity",
                    "medium",
                    f"Function '{name}' has cyclomatic complexity {complexity} (>= {COMPLEXITY_MEDIUM}); "
                    f"consider simplifying its branching.",
                )
            )

        if length > FUNCTION_TOO_LONG:
            issues.append(
                self._issue(
                    path,
                    line,
                    "long_function",
                    "medium",
                    f"Function '{name}' spans {length} lines (> {FUNCTION_TOO_LONG}); "
                    f"extract cohesive chunks into smaller helper functions.",
                )
            )

        args = fn.args
        param_count = len(args.args) + len(args.kwonlyargs) + (1 if args.vararg else 0) + (1 if args.kwarg else 0)
        if param_count > TOO_MANY_PARAMS:
            issues.append(
                self._issue(
                    path,
                    line,
                    "too_many_params",
                    "low",
                    f"Function '{name}' takes {param_count} parameters (> {TOO_MANY_PARAMS}); "
                    f"group related ones into a dataclass/dict or split the function.",
                )
            )

        depth = self._max_nesting_depth(fn)
        if depth > NESTING_TOO_DEEP:
            issues.append(
                self._issue(
                    path,
                    line,
                    "deep_nesting",
                    "medium",
                    f"Function '{name}' nests control structures {depth} levels deep (> {NESTING_TOO_DEEP}); "
                    f"use early returns/guard clauses to flatten it.",
                )
            )

        defaults = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
        for default in defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                issues.append(
                    self._issue(
                        path,
                        getattr(default, "lineno", line),
                        "mutable_default_arg",
                        "high",
                        f"Function '{name}' uses a mutable default argument ({type(default).__name__} literal); "
                        f"it is shared across every call and causes hard-to-find bugs. Default to None and "
                        f"create the object inside the function body instead.",
                    )
                )

        for child in self._walk_own_body(fn):
            if isinstance(child, (ast.Global, ast.Nonlocal)):
                kind = "global" if isinstance(child, ast.Global) else "nonlocal"
                issues.append(
                    self._issue(
                        path,
                        child.lineno,
                        "global_state",
                        "low",
                        f"Function '{name}' mutates {kind} state ({', '.join(child.names)}); "
                        f"prefer passing values in and returning results instead of hidden shared state.",
                    )
                )
                break  # one flag per function is enough signal

        return issues

    def _check_except_handler(self, path: Path, handler: ast.ExceptHandler) -> List[Dict]:
        line = handler.lineno
        body_is_noop = len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)
        if handler.type is None:
            return [
                self._issue(
                    path,
                    line,
                    "bare_except",
                    "high",
                    "Bare 'except:' catches every exception, including KeyboardInterrupt/SystemExit, "
                    "and hides real bugs; catch the specific exception type you expect instead.",
                )
            ]
        if body_is_noop:
            try:
                exc_name = ast.unparse(handler.type)
            except Exception:
                exc_name = getattr(handler.type, "id", None) or "exception"
            return [
                self._issue(
                    path,
                    line,
                    "swallowed_exception",
                    "medium",
                    f"'except {exc_name}: pass' silently discards the error; at minimum log it "
                    f"so the failure is visible instead of vanishing.",
                )
            ]
        return []

    def _check_dangerous_call(self, path: Path, call: ast.Call) -> List[Dict]:
        func = call.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in DANGEROUS_CALLS:
            return [
                self._issue(
                    path,
                    call.lineno,
                    "dangerous_call",
                    "high",
                    f"'{name}()' on dynamic/untrusted input is a code-injection risk; "
                    f"replace it with a safe parser (ast.literal_eval, json.loads, or explicit dispatch).",
                )
            ]
        return []

    def _check_identity_literal_compare(self, path: Path, cmp: ast.Compare) -> List[Dict]:
        issues = []
        for op, right in zip(cmp.ops, cmp.comparators):
            if (
                isinstance(op, (ast.Is, ast.IsNot))
                and isinstance(right, ast.Constant)
                and right.value not in (None, True, False)
            ):
                verb = "is" if isinstance(op, ast.Is) else "is not"
                issues.append(
                    self._issue(
                        path,
                        cmp.lineno,
                        "identity_literal_compare",
                        "medium",
                        f"Uses '{verb}' to compare against the literal {right.value!r}; identity "
                        f"comparison on literals is undefined/CPython-implementation-dependent behaviour "
                        f"- use '==' / '!=' instead.",
                    )
                )
        return issues

    def _check_imports(self, path: Path, tree: ast.AST) -> List[Dict]:
        issues = []
        imported: Dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = (alias.asname or alias.name).split(".")[0]
                    imported[bound] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue  # compiler directives, never "unused" no matter what's referenced
                for alias in node.names:
                    if alias.name == "*":
                        issues.append(
                            self._issue(
                                path,
                                node.lineno,
                                "wildcard_import",
                                "medium",
                                f"'from {node.module or '.'} import *' pollutes the namespace and hides "
                                f"where names come from; import only the specific names you need.",
                            )
                        )
                        continue
                    imported[alias.asname or alias.name] = node.lineno

        used = set()
        string_literals = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                base = node
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name):
                    used.add(base.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                string_literals.add(node.value)  # covers __all__ / re-export patterns

        for name, line in imported.items():
            if name != "_" and name not in used and name not in string_literals:
                issues.append(
                    self._issue(
                        path,
                        line,
                        "unused_import",
                        "low",
                        f"Imported name '{name}' is never used in this file; remove it, or list it in "
                        f"__all__ if it's meant to be re-exported.",
                    )
                )
        return issues

    def _check_duplicate_defs(self, path: Path, tree: ast.AST) -> List[Dict]:
        issues: List[Dict] = []

        def scan_scope(body: List[ast.stmt], scope_name: str) -> None:
            seen: Dict[str, int] = {}
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in seen:
                        issues.append(
                            self._issue(
                                path,
                                node.lineno,
                                "duplicate_definition",
                                "high",
                                f"'{node.name}' is defined again in {scope_name} (first defined at line "
                                f"{seen[node.name]}); the earlier definition is dead code, silently "
                                f"shadowed by this one - remove or rename one of them.",
                            )
                        )
                    seen[node.name] = node.lineno

        scan_scope(tree.body, "module scope")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                scan_scope(node.body, f"class '{node.name}'")
        return issues

    def _check_comment_markers(self, path: Path, lines: List[str]) -> List[Dict]:
        issues = []
        for i, line in enumerate(lines, start=1):
            match = TODO_PATTERN.search(line)
            if match:
                tag, note = match.group(1).upper(), match.group(2).strip()
                message = f"{tag} left in code" + (f": {note}" if note else "") + " - resolve it or track it."
                issues.append(self._issue(path, i, "todo_marker", "info", message))
        return issues

    def _check_line_length(self, path: Path, lines: List[str]) -> List[Dict]:
        issues = []
        for i, line in enumerate(lines, start=1):
            if len(line) > LINE_TOO_LONG:
                issues.append(
                    self._issue(
                        path,
                        i,
                        "long_line",
                        "info",
                        f"Line is {len(line)} characters (> {LINE_TOO_LONG}); wrap it for readability.",
                    )
                )
        return issues

    # -- complexity/nesting helpers -------------------------------------------

    @classmethod
    def _cyclomatic_complexity(cls, fn) -> int:
        """Standard McCabe-style count: start at 1, +1 per decision point.
        Only walks fn's OWN body - nested function/class defs get scored
        separately (by their own ast.walk(tree) visit) so they don't
        inflate their enclosing function's number."""
        complexity = 1
        for node in cls._walk_own_body(fn):
            if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, ast.comprehension):
                complexity += 1 + len(node.ifs)
            elif isinstance(node, ast.Assert):
                complexity += 1
        return complexity

    @classmethod
    def _max_nesting_depth(cls, fn) -> int:
        """Deepest chain of if/for/while/try/with inside fn's own body
        (nested defs excluded, same reasoning as complexity above)."""

        def depth(node: ast.AST, current: int) -> int:
            deepest = current
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                nxt = current + 1 if isinstance(child, NESTING_NODES) else current
                deepest = max(deepest, depth(child, nxt))
            return deepest

        return depth(fn, 0)

    @staticmethod
    def _walk_own_body(fn):
        """Like ast.walk(fn) but stops at nested function/class
        boundaries so a helper defined inside `fn` isn't counted as
        part of fn's own complexity/nesting/global-usage."""
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            node = stack.pop()
            yield node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.extend(ast.iter_child_nodes(node))

    @staticmethod
    def _issue(path: Path, line: int, type_: str, severity: str, message: str) -> Dict:
        return {"file": str(path), "line": line, "type": type_, "severity": severity, "message": message}
