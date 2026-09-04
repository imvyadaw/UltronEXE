class AutomationBuilder:
    def build(self, trigger, actions):
        return {"trigger": trigger, "actions": actions, "requires_policy_check": True}
