import ast
from pathlib import Path


class SkillGenerator:
    def create(self, name, source, directory="skills_generated"):
        ast.parse(source)
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=True)
        f = p / (name + ".py")
        f.write_text(source, encoding="utf-8")
        return {"path": str(f), "validated": True}
