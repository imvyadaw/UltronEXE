"""
Git automation
=================
Thin CLI wrapper (via the `git` command) - clone/status/commit/push/pull
against a working directory, for when the AI needs to drive version
control directly rather than through an IDE.
"""

from typing import Dict, Optional

from apps.base_app import BaseApp


class GitApp(BaseApp):
    """Clone, commit, push, and pull via the Git CLI."""

    APP_NAME = "git"
    PROCESS_NAMES = ["git.exe", "git"]
    EXE_HINTS = ["git", "git.exe"]

    def clone(self, url: str, destination: Optional[str] = None) -> Dict:
        args = ["git", "clone", url]
        if destination:
            args.append(destination)
        return self.run_and_capture(args, timeout=120.0)

    def status(self, repo_path: str) -> Dict:
        return self.run_and_capture(["git", "-C", repo_path, "status", "--short", "--branch"])

    def add_all(self, repo_path: str) -> Dict:
        return self.run_and_capture(["git", "-C", repo_path, "add", "."])

    def commit(self, repo_path: str, message: str) -> Dict:
        return self.run_and_capture(["git", "-C", repo_path, "commit", "-m", message])

    def push(self, repo_path: str, remote: str = "origin", branch: Optional[str] = None) -> Dict:
        args = ["git", "-C", repo_path, "push", remote]
        if branch:
            args.append(branch)
        return self.run_and_capture(args, timeout=60.0)

    def pull(self, repo_path: str) -> Dict:
        return self.run_and_capture(["git", "-C", repo_path, "pull"], timeout=60.0)

    def current_branch(self, repo_path: str) -> Dict:
        result = self.run_and_capture(["git", "-C", repo_path, "branch", "--show-current"])
        if result.get("success"):
            result["branch"] = result["stdout"].strip()
        return result

    def create_branch(self, repo_path: str, branch_name: str) -> Dict:
        return self.run_and_capture(["git", "-C", repo_path, "checkout", "-b", branch_name])

    def log(self, repo_path: str, count: int = 10) -> Dict:
        result = self.run_and_capture(["git", "-C", repo_path, "log", f"-{count}", "--oneline"])
        if result.get("success"):
            result["commits"] = [line for line in result["stdout"].splitlines() if line.strip()]
        return result
