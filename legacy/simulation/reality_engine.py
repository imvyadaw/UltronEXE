from .scenario_engine import ScenarioEngine


class RealityEngine:
    def simulate(self, state, actions):
        return ScenarioEngine().branch(state, actions)
