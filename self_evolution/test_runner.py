import os
import subprocess
import sys


class TestRunner:
    def run(self, root):
        """Run the project's tests from the sandbox with the sandbox root on PYTHONPATH.

        Returns a structured failure on timeout/launch errors instead of raising.
        """
        root = os.path.abspath(str(root))
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root + (os.pathsep + existing if existing else "")
        try:
            p = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {
                "success": p.returncode == 0,
                "returncode": p.returncode,
                "stdout": p.stdout[-10000:],
                "stderr": p.stderr[-10000:],
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "returncode": None,
                "stdout": (exc.stdout or "")[-10000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-10000:] if isinstance(exc.stderr, str) else "",
                "error": "test suite timed out after 300 seconds",
            }
        except OSError as exc:
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "error": f"unable to start test runner: {exc}",
            }
