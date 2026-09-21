from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class SecurityContext:
    user_id: str
    session_id: str
    action: str
    resource: str
    metadata: Dict[str, Any]
    
    @classmethod
    def default(cls) -> "SecurityContext":
        return cls(
            user_id="anonymous",
            session_id="none",
            action="unknown",
            resource="unknown",
            metadata={}
        )
