import subprocess, sys


class TestingAgent:
    def run(self, path="."):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"], cwd=path, capture_output=True, text=True, timeout=300
        )
        return {"success": p.returncode == 0, "stdout": p.stdout[-8000:], "stderr": p.stderr[-8000:]}
