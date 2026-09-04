from cognitive_core.goal_planner import get_goal_planner


class Planner:
    def __init__(self):
        self.backend = get_goal_planner()

    def plan(self, goal, feedback=None):
        return self.backend.plan_goal(goal, feedback)

    def quick_plan(self, goal):
        return self.backend.quick_plan(goal)
