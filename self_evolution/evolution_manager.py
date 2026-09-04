"""
Evolution manager
==================
Ties the rest of self_evolution/ together: analyze -> identify
improvements -> generate + apply patches (sandbox only) -> compile ->
test -> validate -> record. Transactional in the sense that nothing
here is accepted or recorded unless the sandbox compiles AND its test
suite passes after the patches are applied.

It deliberately does not patch production automatically - every patch
is generated and applied against sandbox.py's throwaway
tempfile.mkdtemp() copy, never against project_root itself. Promoting
an accepted, recorded version from sandbox back into the real project
is a separate, human-approved step (Priority 10's "human approval ->
deploy") that this module does not perform; a caller reviews
evaluate()'s returned "patches" (each with a unified diff) and
version_manager.py's record before ever touching the real codebase.
"""

import os

from self_evolution.code_analyzer import CodeAnalyzer
from self_evolution.improvement_engine import ImprovementEngine
from self_evolution.patch_generator import PatchGenerator
from self_evolution.sandbox import EvolutionSandbox
from self_evolution.test_runner import TestRunner
from self_evolution.validator import Validator
from self_evolution.version_manager import VersionManager


class EvolutionManager:
    def __init__(self):
        self.analyzer = CodeAnalyzer()
        self.improver = ImprovementEngine()
        self.patcher = PatchGenerator()
        self.sandbox = EvolutionSandbox()
        self.runner = TestRunner()
        self.validator = Validator()
        self.versions = VersionManager()

    def evaluate(self, project_root):
        analysis = self.analyzer.analyze(project_root)
        issues = self.improver.identify(analysis)
        sandbox = self.sandbox.create(project_root)

        # code_analyzer.py walks project_root and records each issue's
        # "file" as an absolute path INTO project_root (e.g.
        # "/real/project/broken.py") - patch_generator.py must never
        # resolve that against the real project, only against the
        # sandbox copy, or a successful patch would land on the real
        # file instead of the throwaway one. Re-root every path to be
        # relative to project_root here, once, before any issue reaches
        # the patcher, so _resolve()'s "absolute path = use as-is" branch
        # can only ever mean "absolute path into the sandbox" from here on.
        for issue in issues:
            issue["file"] = os.path.relpath(issue["file"], project_root)

        # Generate + apply every proposed patch inside the sandbox copy
        # only. A failed/no-change proposal for one issue never blocks
        # the others - each is independent.
        patches = []
        for issue in issues:
            proposal = self.patcher.propose(issue, sandbox)
            if proposal["status"] == "proposed":
                applied = self.patcher.apply(proposal)
                proposal["applied"] = applied["success"]
                if not applied["success"]:
                    proposal["error"] = applied["error"]
            patches.append(proposal)

        compiled = self.validator.compile(sandbox)
        tests = self.runner.run(sandbox) if compiled["success"] else {"success": False, "error": "compile failed"}
        accepted = compiled["success"] and self.validator.accept(tests)
        version = self.versions.record("sandbox evaluation", tests, sandbox) if accepted else None
        return {
            "accepted": accepted,
            "analysis": analysis,
            "patches": patches,
            "compile": compiled,
            "tests": tests,
            "version": version,
            "sandbox": str(sandbox),
        }
