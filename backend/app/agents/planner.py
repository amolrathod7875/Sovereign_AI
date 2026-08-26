import logging
from typing import List
from app.schemas import TaskType

logger = logging.getLogger(__name__)


def classify_task(message: str, attachments: List[str]) -> str:
    """
    Classify the task based on user message and attachments.

    Returns a TaskType string.
    """
    message_lower = message.lower()

    has_image = any(
        ext in attachment.lower()
        for attachment in attachments
        for ext in [".png", ".jpg", ".jpeg", ".pdf", ".gif", ".bmp", ".webp"]
    )

    if has_image and any(
        keyword in message_lower
        for keyword in ["image", "picture", "photo", "drawing", "diagram", "visual", "scan"]
    ):
        return TaskType.MULTIMODAL_ANALYSIS

    if any(
        keyword in message_lower
        for keyword in ["code", "python", "script", "function", "debug", "programming"]
    ):
        return TaskType.CODING

    if any(
        keyword in message_lower
        for keyword in ["analyze", "calculate", "csv", "spreadsheet", "data", "downtime", "average", "sum"]
    ):
        return TaskType.DATA_ANALYSIS

    if any(
        keyword in message_lower
        for keyword in ["approval", "note", "document", "report", "memo", "letter", "generate"]
    ):
        return TaskType.DOCUMENT_GENERATION

    if any(
        keyword in message_lower
        for keyword in ["presentation", "slide", "pptx", "board"]
    ):
        return TaskType.PRESENTATION_GENERATION

    if any(
        keyword in message_lower
        for keyword in ["search", "find", "look up", "what does", "how do", "tell me about"]
    ):
        return TaskType.RAG_QA

    return TaskType.GENERAL_QA


def create_plan(task_type: str, message: str) -> List[str]:
    """
    Create an execution plan based on task type.
    """
    plans = {
        TaskType.DOCUMENT_ANALYSIS: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "process_document",
            "run_ocr",
            "hybrid_retrieval",
            "analyze_and_reason",
            "generate_artifact",
            "finalize",
        ],
        TaskType.CODING: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "generate_code",
            "validate_code",
            "execute_in_sandbox",
            "verify_result",
            "store_artifact",
            "finalize",
        ],
        TaskType.DATA_ANALYSIS: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "generate_analysis_code",
            "execute_in_sandbox",
            "generate_spreadsheet",
            "finalize",
        ],
        TaskType.RAG_QA: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "hybrid_retrieval",
            "generate_answer",
            "finalize",
        ],
        TaskType.MULTIMODAL_ANALYSIS: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "process_image",
            "analyze_with_vlm",
            "finalize",
        ],
        TaskType.DOCUMENT_GENERATION: [
            "validate_inputs",
            "classify_task",
            "select_model",
            "gather_context",
            "generate_document",
            "finalize",
        ],
    }

    return plans.get(task_type, ["validate_inputs", "classify_task", "select_model", "generate_response", "finalize"])
