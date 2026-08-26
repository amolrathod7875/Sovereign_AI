import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger for tracking all agent actions.
    """

    def __init__(self):
        self.audit_records: List[Dict[str, Any]] = []

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: str = None,
        execution_id: str = None,
    ):
        """
        Log an audit event.
        """
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
            "user_id": user_id,
            "execution_id": execution_id,
        }

        self.audit_records.append(record)

        if len(self.audit_records) > 10000:
            self.audit_records.pop(0)

        logger.info(f"AUDIT: {action} on {entity_type}/{entity_id} by {user_id or 'system'}")

        return record

    def log_model_invocation(
        self,
        model_id: str,
        task_type: str,
        execution_id: str,
        duration_ms: int,
        success: bool,
    ):
        """
        Log a model invocation.
        """
        return self.log(
            action="MODEL_INVOKED",
            entity_type="model",
            entity_id=model_id,
            details={
                "task_type": task_type,
                "duration_ms": duration_ms,
                "success": success,
            },
            execution_id=execution_id,
        )

    def log_tool_execution(
        self,
        tool_name: str,
        execution_id: str,
        duration_ms: int,
        success: bool,
        error: str = None,
    ):
        """
        Log a tool execution.
        """
        return self.log(
            action="TOOL_EXECUTED",
            entity_type="tool",
            entity_id=tool_name,
            details={
                "duration_ms": duration_ms,
                "success": success,
                "error": error,
            },
            execution_id=execution_id,
        )

    def log_artifact_created(
        self,
        artifact_id: str,
        artifact_type: str,
        execution_id: str,
        filename: str,
    ):
        """
        Log artifact creation.
        """
        return self.log(
            action="ARTIFACT_CREATED",
            entity_type="artifact",
            entity_id=artifact_id,
            details={
                "artifact_type": artifact_type,
                "filename": filename,
            },
            execution_id=execution_id,
        )

    def get_records(
        self,
        execution_id: str = None,
        action: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get audit records with optional filtering.
        """
        records = self.audit_records

        if execution_id:
            records = [r for r in records if r.get("execution_id") == execution_id]

        if action:
            records = [r for r in records if r.get("action") == action]

        return records[-limit:]


audit_logger = AuditLogger()
