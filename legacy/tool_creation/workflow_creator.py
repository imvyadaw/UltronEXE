class WorkflowCreator:
    def create(self, name, steps):
        if not steps:
            raise ValueError("workflow requires steps")
        return {"name": name, "steps": steps}
