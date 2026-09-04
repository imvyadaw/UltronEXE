"""
api_doc_reader.py
====================
Turns API documentation you already have on disk - an OpenAPI/Swagger
JSON or YAML file, or a plain markdown doc with fenced request
examples - into a structured list of `APIEndpoint`s that
`skill_code_generator.py` can turn into a scaffold.

This module only reads files you point it at locally; it does not
fetch URLs itself. If the docs live online, save/export them first
(most API providers offer a raw OpenAPI spec URL) - keeping the fetch
step separate and visible means you always know exactly what spec
version a generated skill was built against.

Pure standard library (YAML support is optional - falls back to
JSON-only parsing if `pyyaml` isn't installed).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ultron.api_doc_reader")

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@dataclass
class APIEndpoint:
    path: str
    method: str
    summary: str = ""
    parameters: List[Dict] = field(default_factory=list)  # [{"name","in","required","type"}]
    request_body_schema: Optional[Dict] = None
    auth_required: bool = True

    def signature_hint(self) -> str:
        required = [p["name"] for p in self.parameters if p.get("required")]
        optional = [p["name"] for p in self.parameters if not p.get("required")]
        parts = required + [f"{o}=None" for o in optional]
        return ", ".join(parts)


class APIDocReader:
    """Reads a local OpenAPI spec (JSON/YAML) or a markdown doc with
    fenced ```http or ```curl request blocks, and produces `APIEndpoint`s."""

    def read_openapi(self, path: str) -> List[APIEndpoint]:
        text = Path(path).read_text()
        spec = self._parse_structured(text, path)
        endpoints: List[APIEndpoint] = []

        paths = spec.get("paths", {})
        for path_str, methods in paths.items():
            for method, details in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                params = []
                for p in details.get("parameters", []):
                    params.append(
                        {
                            "name": p.get("name"),
                            "in": p.get("in", "query"),
                            "required": p.get("required", False),
                            "type": (p.get("schema") or {}).get("type", "string"),
                        }
                    )
                body_schema = None
                body = details.get("requestBody", {})
                content = body.get("content", {})
                if "application/json" in content:
                    body_schema = content["application/json"].get("schema")

                endpoints.append(
                    APIEndpoint(
                        path=path_str,
                        method=method.upper(),
                        summary=details.get("summary", ""),
                        parameters=params,
                        request_body_schema=body_schema,
                        auth_required="security" in details or "security" in spec,
                    )
                )
        logger.info("Parsed %d endpoints from %s", len(endpoints), path)
        return endpoints

    def read_markdown(self, path: str) -> List[APIEndpoint]:
        """Best-effort extraction from fenced ```http blocks like:

        ```http
        GET /v1/widgets/{id}
        ```
        """
        text = Path(path).read_text()
        endpoints: List[APIEndpoint] = []
        for block in re.findall(r"```(?:http|curl)?\n(.*?)```", text, re.DOTALL):
            match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", block, re.IGNORECASE)
            if not match:
                continue
            method, path_str = match.group(1).upper(), match.group(2)
            param_names = re.findall(r"\{(\w+)\}", path_str)
            endpoints.append(
                APIEndpoint(
                    path=path_str,
                    method=method,
                    parameters=[{"name": n, "in": "path", "required": True, "type": "string"} for n in param_names],
                )
            )
        logger.info("Parsed %d endpoints from markdown %s", len(endpoints), path)
        return endpoints

    def _parse_structured(self, text: str, path: str) -> dict:
        if path.endswith((".yaml", ".yml")):
            if not _HAS_YAML:
                raise RuntimeError("pyyaml not installed - `pip install pyyaml` or convert to JSON")
            return yaml.safe_load(text)
        return json.loads(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo_spec = {
        "paths": {
            "/v1/widgets/{id}": {
                "get": {
                    "summary": "Fetch a widget by id",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                }
            }
        }
    }
    demo_path = Path("ultron_data/skill_creator/_demo_spec.json")
    demo_path.parent.mkdir(parents=True, exist_ok=True)
    demo_path.write_text(json.dumps(demo_spec))

    reader = APIDocReader()
    for ep in reader.read_openapi(str(demo_path)):
        print(ep.method, ep.path, "->", ep.signature_hint())
