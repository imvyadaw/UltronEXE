class ScenarioEngine:
    def branch(self, base, alternatives):
        return [{"base": base, "alternative": x} for x in alternatives]
