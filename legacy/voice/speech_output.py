class SpeechOutput:
    def __init__(self):
        from voice import get_voice

        self.engine = get_voice()

    def speak(self, text):
        return self.engine.speak(text)
