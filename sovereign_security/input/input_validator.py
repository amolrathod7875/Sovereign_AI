from .file_guard import FileGuard
from .path_guard import PathGuard
from .mime_guard import MimeGuard

class InputValidator:
    def __init__(self, allowed_roots=None):
        self.file_guard = FileGuard()
        self.path_guard = PathGuard(allowed_roots)
        self.mime_guard = MimeGuard()

    def validate_file(self, file_path: str):
        self.path_guard.enforce(file_path)
        self.file_guard.enforce(file_path)
        
        # Mime guard just warns if it's unknown, but we evaluate it
        decision = self.mime_guard.evaluate(file_path)
        if not decision.allowed:
            self.mime_guard.enforce(file_path)

    def validate(self, input_data: dict):
        file_path = input_data.get("file_path")
        if file_path:
            # We return a SecurityDecision instead of throwing
            from ..core.decision import SecurityDecision
            try:
                self.validate_file(file_path)
                return SecurityDecision.allow(domain="INPUT", reason="Valid input file")
            except Exception as e:
                return SecurityDecision.deny(domain="INPUT", reason=str(e))
        return SecurityDecision.allow(domain="INPUT", reason="No file path provided")
