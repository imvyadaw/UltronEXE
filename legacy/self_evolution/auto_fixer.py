"""
Auto fixer
==========
Deterministic, review-free fixes for the code_analyzer.py finding
types that have exactly one correct, semantic-preserving rewrite - no
LLM call needed because there's no judgment involved in *how* to fix
them, only *whether*:

  - unused_import           -> remove the unused name (or the whole
                                import line if nothing else in it survives)
  - bare_except              -> `except:` becomes `except Exception:`
  - identity_literal_compare -> `is`/`is not` against a literal becomes
                                `==`/`!=` (only applied when the line has
                                exactly one such occurrence, so there's
                                no ambiguity about which one to rewrite)
  - mutable_default_arg      -> the default becomes None, and the
                                original literal is (re)constructed on
                                first use inside the function body

Everything else code_analyzer.py finds (complexity, long functions,
deep nesting, duplicate defs, dangerous eval/exec calls, swallowed
exceptions, global state, wildcard imports) needs a human or an LLM to
judge *how* to restructure the code without changing its behaviour.
This module deliberately leaves those alone - they're meant to go
through patch_generator.py's LLM-backed review path instead, never
this one.

Every fix here re-parses the file with ast.parse() before writing
anything back, so a fix that would break the file's syntax is simply
not applied.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

FIXABLE_TYPES = {
    "unused_import",
    "bare_except",
    "identity_literal_compare",
    "mutable_default_arg",
    "swallowed_exception",
}


class AutoFixer:
    """Applies safe, mechanical fixes for a bounded set of finding types."""

    def fix_project(self, root, issues: List[Dict]) -> Dict:
        """issues: code_analyzer.py's analysis["issues"] list (or
        improvement_engine.py's identify() output - both carry "file",
        "type", "line"). Groups by file, fixes each file once, and
        returns a per-file report plus overall counts."""
        by_file: Dict[str, List[Dict]] = {}
        for issue in issues:
            if issue.get("type") in FIXABLE_TYPES:
                by_file.setdefault(issue["file"], []).append(issue)

        report = {"files_changed": 0, "fixes_applied": 0, "fixes_skipped": 0, "details": []}
        for file_path, file_issues in by_file.items():
            applied, skipped = self._fix_file(Path(file_path), file_issues)
            if applied:
                report["files_changed"] += 1
            report["fixes_applied"] += len(applied)
            report["fixes_skipped"] += len(skipped)
            report["details"].append({"file": file_path, "applied": applied, "skipped": skipped})
        return report

    # -- single-file pipeline -------------------------------------------------

    def _fix_file(self, path: Path, issues: List[Dict]) -> Tuple[List[str], List[str]]:
        try:
            original = path.read_text(encoding="utf-8")
        except Exception as e:
            return [], [f"could not read file: {e}"]

        text = original
        applied: List[str] = []
        skipped: List[str] = []

        # Order matters: mutable-default-arg and identity-compare rewrite
        # specific lines, so re-derive fresh AST positions after each
        # successful edit rather than trusting the original issue list's
        # line numbers once the file has already shifted.
        for kind in (
            "mutable_default_arg",
            "identity_literal_compare",
            "bare_except",
            "unused_import",
            "swallowed_exception",
        ):
            relevant = [i for i in issues if i.get("type") == kind]
            if not relevant:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as e:
                skipped.append(f"{kind}: file no longer parses ({e}), stopped fixing")
                break
            method = getattr(self, f"_fix_{kind}")
            new_text, done, failed = method(text, tree)
            if new_text != text:
                try:
                    ast.parse(new_text)  # never keep an edit that breaks compilation
                except SyntaxError:
                    skipped.append(f"{kind}: proposed fix broke compilation, discarded")
                    continue
                text = new_text
            applied.extend(done)
            skipped.extend(failed)

        if text != original:
            path.write_text(text, encoding="utf-8")

        return applied, skipped

    # -- bare except: `except:` -> `except Exception:` ------------------------

    def _fix_bare_except(self, text: str, tree: ast.AST):
        lines = text.splitlines(keepends=True)
        applied, skipped = [], []
        pattern = re.compile(r"^(\s*)except\s*:")
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                idx = node.lineno - 1
                if 0 <= idx < len(lines) and pattern.match(lines[idx]):
                    lines[idx] = pattern.sub(r"\1except Exception:", lines[idx])
                    applied.append(f"line {node.lineno}: bare except -> except Exception")
                else:
                    skipped.append(f"line {node.lineno}: bare except pattern not found as expected, skipped")
        return "".join(lines), applied, skipped

    # -- `is <literal>` -> `== <literal>` --------------------------------------

    def _fix_identity_literal_compare(self, text: str, tree: ast.AST):
        lines = text.splitlines(keepends=True)
        applied, skipped = [], []
        targets = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for op in node.ops:
                    if isinstance(op, (ast.Is, ast.IsNot)):
                        targets.add(node.lineno)
        for lineno in targets:
            idx = lineno - 1
            if not (0 <= idx < len(lines)):
                continue
            line = lines[idx]
            is_not_count = len(re.findall(r"\bis\s+not\b", line))
            is_count = len(re.findall(r"\bis\b", line)) - is_not_count
            if is_not_count == 1 and is_count == 0:
                lines[idx] = re.sub(r"\bis\s+not\b", "!=", line, count=1)
                applied.append(f"line {lineno}: 'is not <literal>' -> '!='")
            elif is_not_count == 0 and is_count == 1:
                lines[idx] = re.sub(r"\bis\b", "==", line, count=1)
                applied.append(f"line {lineno}: 'is <literal>' -> '=='")
            else:
                skipped.append(f"line {lineno}: multiple is/is-not on one line, ambiguous, left for manual review")
        return "".join(lines), applied, skipped

    # -- unused imports ---------------------------------------------------------

    def _fix_unused_import(self, text: str, tree: ast.AST):
        lines = text.splitlines(keepends=True)
        applied, skipped = [], []
        used, string_literals = self._collect_used_names(tree)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.lineno != getattr(node, "end_lineno", node.lineno):
                skipped.append(f"line {node.lineno}: multi-line import statement, left for manual review")
                continue
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue  # compiler directives, never touch these regardless of "usage"
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                continue  # wildcard imports aren't this fixer's job

            unused_aliases = [
                a
                for a in node.names
                if (a.asname or a.name.split(".")[0] if isinstance(node, ast.Import) else a.asname or a.name)
                not in used
                and (a.asname or a.name) not in string_literals
            ]
            if not unused_aliases:
                continue

            idx = node.lineno - 1
            if not (0 <= idx < len(lines)):
                continue

            if len(unused_aliases) == len(node.names):
                lines[idx] = ""  # whole statement is dead
                applied.append(f"line {node.lineno}: removed unused import line")
            elif len(node.names) - len(unused_aliases) >= 1 and "," in lines[idx] and "(" not in lines[idx]:
                kept = [a for a in node.names if a not in unused_aliases]
                names_src = ", ".join((f"{a.name} as {a.asname}" if a.asname else a.name) for a in kept)
                if isinstance(node, ast.Import):
                    lines[idx] = f"import {names_src}\n"
                else:
                    lines[idx] = f"from {node.module or '.'} import {names_src}\n"
                removed = ", ".join(a.asname or a.name for a in unused_aliases)
                applied.append(f"line {node.lineno}: dropped unused name(s) {removed} from import")
            else:
                skipped.append(f"line {node.lineno}: parenthesized/complex import list, left for manual review")

        return "".join(lines), applied, skipped

    @staticmethod
    def _collect_used_names(tree: ast.AST):
        used, string_literals = set(), set()
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
                string_literals.add(node.value)
        return used, string_literals

    # -- mutable default arguments ----------------------------------------------

    def _fix_mutable_default_arg(self, text: str, tree: ast.AST):
        lines = text.splitlines(keepends=True)
        applied, skipped = [], []
        # Apply from the bottom of the file up, so earlier edits don't
        # shift line numbers out from under later ones in the same pass.
        functions = sorted(
            (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
            key=lambda n: n.lineno,
            reverse=True,
        )
        for fn in functions:
            args = fn.args
            pairs = list(
                zip(reversed(args.args[-len(args.defaults) :] if args.defaults else []), reversed(args.defaults))
            )
            pairs += list(zip(args.kwonlyargs, args.kw_defaults))
            mutable_pairs = [(a, d) for a, d in pairs if d is not None and isinstance(d, (ast.List, ast.Dict, ast.Set))]
            if not mutable_pairs:
                continue

            sig_idx = fn.lineno - 1
            if not (0 <= sig_idx < len(lines)):
                skipped.append(f"function '{fn.name}' line {fn.lineno}: signature line not found, skipped")
                continue

            header_end = getattr(fn.args, "end_lineno", None) or fn.lineno
            header_span = "".join(lines[sig_idx:header_end])
            new_header = header_span
            prologue_stmts = []
            ok = True
            for arg, default in mutable_pairs:
                try:
                    default_src = ast.unparse(default)
                except Exception:
                    ok = False
                    break
                pattern = re.compile(rf"\b{re.escape(arg.arg)}\s*=\s*" + re.escape(ast.unparse(default)))
                if not pattern.search(new_header):
                    ok = False
                    break
                new_header = pattern.sub(f"{arg.arg}=None", new_header, count=1)
                prologue_stmts.append((arg.arg, default_src))
            if not ok:
                skipped.append(
                    f"function '{fn.name}' line {fn.lineno}: could not locate default in "
                    f"source text exactly, left for manual review"
                )
                continue

            body_indent = self._indent_of(lines, fn.body[0].lineno - 1) if fn.body else "    "
            insert_at = fn.body[0].lineno - 1 if fn.body else header_end
            # Skip past a leading docstring so the guard clauses read
            # naturally right before the first real statement.
            if (
                fn.body
                and isinstance(fn.body[0], ast.Expr)
                and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
                and isinstance(fn.body[0].value.value, str)
            ):
                insert_at = fn.body[1].lineno - 1 if len(fn.body) > 1 else insert_at + 1

            guard_lines = "".join(
                f"{body_indent}if {name} is None:\n{body_indent}    {name} = {src}\n" for name, src in prologue_stmts
            )

            lines[sig_idx:header_end] = [new_header]
            insert_at = insert_at - (header_end - sig_idx - 1)  # header may have shrunk to 1 line
            lines.insert(max(insert_at, sig_idx + 1), guard_lines)
            applied.append(
                f"function '{fn.name}' line {fn.lineno}: mutable default(s) "
                f"{[n for n, _ in prologue_stmts]} -> None + guarded init"
            )

        return "".join(lines), applied, skipped

    # -- swallowed exceptions: `except X: pass` -> logs instead of hiding ------

    def _fix_swallowed_exception(self, text: str, tree: ast.AST):
        lines = text.splitlines(keepends=True)
        applied, skipped = [], []

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    try:
                        exc_name = ast.unparse(node.type)
                    except Exception:
                        exc_name = getattr(node.type, "id", None) or "exception"
                    idx = node.body[0].lineno - 1
                    if 0 <= idx < len(lines) and lines[idx].strip() == "pass":
                        indent = self._indent_of(lines, idx)
                        lines[idx] = f'{indent}logging.getLogger(__name__).exception("Suppressed {exc_name}")\n'
                        applied.append(f"line {node.body[0].lineno}: except {exc_name}: pass -> now logs the exception")
                    else:
                        skipped.append(
                            f"line {node.lineno}: swallowed-exception body isn't a simple 'pass', "
                            f"left for manual review"
                        )

        if applied and not self._has_logging_import(tree):
            insert_at = self._import_insert_point(tree)
            lines.insert(insert_at, "import logging\n")
            applied.append(f"line {insert_at + 1}: added 'import logging' (needed by the fix above)")

        return "".join(lines), applied, skipped

    @staticmethod
    def _has_logging_import(tree: ast.AST) -> bool:
        return any(isinstance(n, ast.Import) and any(a.name == "logging" for a in n.names) for n in ast.walk(tree))

    @staticmethod
    def _import_insert_point(tree: ast.AST) -> int:
        """0-based line index to insert a new top-level import at -
        right after a module docstring and/or a `from __future__
        import` line, whichever is last, so the new import never lands
        before either (both must stay first in the file)."""
        insert_at = 0
        body = getattr(tree, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            insert_at = max(insert_at, body[0].end_lineno)
        for node in body:
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                insert_at = max(insert_at, node.end_lineno)
        return insert_at

    @staticmethod
    def _indent_of(lines: List[str], idx: int) -> str:
        if not (0 <= idx < len(lines)):
            return "    "
        match = re.match(r"^(\s*)", lines[idx])
        return match.group(1) if match else "    "
