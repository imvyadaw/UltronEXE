class ULTRONBridge:
    def brain(self):
        from core.brain import get_brain

        return get_brain()

    def runtime(self):
        from core.assistant import Assistant

        return Assistant()
