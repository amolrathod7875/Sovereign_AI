from .secret_detector import SecretDetector

class Redactor:
    def __init__(self):
        self.detector = SecretDetector()

    def redact(self, text: str) -> str:
        return self.detector.redact(text)
