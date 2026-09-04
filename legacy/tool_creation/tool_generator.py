import ast


class ToolGenerator:
    def validate(self, source):
        ast.parse(source)
        return {"valid": True}

    def generate(self, name, source):
        self.validate(source)
        return {"name": name, "source": source, "activation": "sandbox_only"}
