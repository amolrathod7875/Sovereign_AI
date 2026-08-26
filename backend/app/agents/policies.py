from typing import Dict, List, Any
from app.schemas import TaskType
from app.models.router import route_task


def determine_routing(task_type: str, has_image: bool, state: Dict) -> str:
    """
    Determine which model to use based on task type and current state.
    """
    return route_task(task_type, has_image)


def get_required_tools(task_type: str) -> List[str]:
    """
    Determine which tools are needed based on task type.
    """
    tool_map = {
        TaskType.DOCUMENT_ANALYSIS: ["ocr", "rag", "docx_generator"],
        TaskType.CODING: ["python_generator", "sandbox"],
        TaskType.DATA_ANALYSIS: ["python_generator", "sandbox", "spreadsheet_generator"],
        TaskType.RAG_QA: ["rag"],
        TaskType.MULTIMODAL_ANALYSIS: ["vision", "rag"],
        TaskType.DOCUMENT_GENERATION: ["docx_generator", "rag"],
        TaskType.PRESENTATION_GENERATION: ["pptx_generator", "rag"],
        TaskType.GENERAL_QA: [],
    }
    return tool_map.get(task_type, [])


def get_retrieval_enabled(task_type: str) -> bool:
    """
    Determine if RAG should be enabled for this task type.
    """
    rag_enabled_types = [
        TaskType.RAG_QA,
        TaskType.DOCUMENT_ANALYSIS,
        TaskType.DOCUMENT_GENERATION,
        TaskType.CORRESPONDENCE_SEARCH,
        TaskType.MULTIMODAL_ANALYSIS,
    ]
    return task_type in rag_enabled_types
