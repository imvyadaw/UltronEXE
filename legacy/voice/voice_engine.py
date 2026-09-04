class VoiceEngine:
    def __init__(self):
        from voice import get_voice, get_stt

        self.tts = get_voice()
        self.stt = get_stt()

    def run_once(self, orchestrator):
        text = self.stt.transcribe_from_mic()
        if not text:
            return {"success": False, "error": "No speech recognized"}
        result = orchestrator.run(text)
        self.tts.speak(str(result))
        return result
