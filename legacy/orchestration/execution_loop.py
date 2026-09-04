class ExecutionLoop:
    def __init__(self, executor):
        self.executor = executor

    def run(self, goal, **kw):
        return self.executor.run_goal(goal, **kw)
