import compileall


class Validator:
    def compile(self, root):
        return {"success": bool(compileall.compile_dir(str(root), quiet=1))}

    def accept(self, test_result):
        return bool(test_result.get("success"))
