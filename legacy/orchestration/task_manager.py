from ULTRON_CORE.common import Task


class TaskManager:
    def __init__(self):
        self.tasks = {}

    def add(self, title, deps=None):
        t = Task(title, dependencies=deps or [])
        self.tasks[t.id] = t
        return t

    def ready(self):
        done = {x.id for x in self.tasks.values() if x.status == "completed"}
        return [x for x in self.tasks.values() if x.status == "pending" and all(d in done for d in x.dependencies)]
