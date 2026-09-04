from pathlib import Path
import json, time


class VersionManager:
    def __init__(self, path="storage/ultron_versions.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, summary, test_result, rollback):
        d = json.loads(self.path.read_text()) if self.path.exists() else []
        e = {
            "version": len(d) + 1,
            "timestamp": time.time(),
            "summary": summary,
            "test_result": test_result,
            "rollback": str(rollback),
        }
        d.append(e)
        self.path.write_text(json.dumps(d, indent=2, default=str))
        return e
