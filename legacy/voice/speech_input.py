class SpeechInput:
    def __init__(self):
        from voice import get_stt

        self.engine = get_stt()

    def listen(self):
        return self.engine.transcribe_from_mic()
