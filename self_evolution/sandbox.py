from pathlib import Path
import tempfile, shutil


class EvolutionSandbox:
    def create(self, source):
        d = Path(tempfile.mkdtemp(prefix="ultron_ultron_")) / "project"
        shutil.copytree(source, d)
        return d
