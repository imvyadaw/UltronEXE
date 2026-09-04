"""Final ULTRON runtime tool-audit helper.

This is intentionally a wiring/health audit, not a fake "all tools passed"
test. It imports the real runtime registry and dispatch layer, then reports
which registered tools have a live dispatch route. It does NOT execute tools,
because doing so blindly could delete files, shut down Windows, send messages,
modify settings, or perform network actions.

Run from the ULTRON project root on the target Windows environment:
    python tools/final_runtime_audit.py
    python tools/final_runtime_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Ensure the project root is importable when this file is launched directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ULTRON tool registry and dispatch wiring.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    try:
        from ai.tools_schema import TOOLS
        from ai import tool_runtime
        from core.capability_registry import get_capability_registry
    except Exception as exc:
        result = {
            "status": "IMPORT_FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "project_root": str(ROOT),
            "hint": "Run this on the intended Windows environment with requirements installed.",
        }
        print(json.dumps(result, indent=2) if args.json else f"IMPORT_FAILED: {type(exc).__name__}: {exc}")
        return 2

    names = []
    malformed = 0
    for entry in TOOLS:
        try:
            name = entry["function"]["name"]
        except (KeyError, TypeError):
            malformed += 1
            continue
        if name:
            names.append(name)

    unique = set(names)
    direct = set(getattr(tool_runtime, "_DIRECT_HANDLERS", {}))
    arg_map = set(getattr(tool_runtime, "TOOL_ARG_MAP", {}))
    routes = direct | arg_map

    registry = get_capability_registry()
    registry.bootstrap()
    registered = {c.name for c in registry.list_by_category("tool")}

    dispatch_missing = sorted(unique - routes)
    registry_missing = sorted(unique - registered)
    duplicate_names = sorted(n for n, count in Counter(names).items() if count > 1)

    result = {
        "status": "PASS" if not dispatch_missing and not registry_missing and malformed == 0 else "REVIEW",
        "schema_tools": len(names),
        "unique_schema_tools": len(unique),
        "direct_handlers": len(direct),
        "arg_map_routes": len(arg_map),
        "tools_with_dispatch_route": len(unique & routes),
        "capability_registry_tools": len(registered),
        "dispatch_missing": dispatch_missing,
        "registry_missing": registry_missing,
        "malformed_schema_entries": malformed,
        "duplicate_schema_names": duplicate_names,
        "note": "No tool is executed by this audit. Live side-effect verification must be done separately and safely on Windows.",
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("ULTRON FINAL RUNTIME WIRING AUDIT")
        print("=" * 34)
        for key in (
            "status",
            "schema_tools",
            "unique_schema_tools",
            "direct_handlers",
            "arg_map_routes",
            "tools_with_dispatch_route",
            "capability_registry_tools",
            "malformed_schema_entries",
        ):
            print(f"{key}: {result[key]}")
        print(f"dispatch_missing: {len(dispatch_missing)}")
        print(f"registry_missing: {len(registry_missing)}")
        print(f"duplicate_schema_names: {len(duplicate_names)}")
        if dispatch_missing:
            print("\nFirst missing dispatch routes:")
            print("\n".join(f"  - {n}" for n in dispatch_missing[:50]))
        if registry_missing:
            print("\nFirst missing registry entries:")
            print("\n".join(f"  - {n}" for n in registry_missing[:50]))
        print("\nIMPORTANT: This checks wiring only; it deliberately does not execute tools.")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
