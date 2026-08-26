from app.models.registry import model_registry, update_model_status
from app.schemas import TaskType


def route_task(task_type: str, has_image: bool = False) -> str:
    """
    Route a task to the appropriate model based on task type and input.

    Routing rules (deterministic, explainable):
    - If image/drawing present AND task involves visual understanding -> VLM
    - If task requires code execution -> Coder LLM
    - If request is grounded in internal documents -> RAG + General LLM
    - If deliverable is requested -> General LLM + appropriate output tool
    - Default -> General LLM
    """

    if has_image and task_type in [
        TaskType.MULTIMODAL_ANALYSIS,
        TaskType.DOCUMENT_ANALYSIS,
    ]:
        model_id = "vision"
        update_model_status("vision", "active")
        return model_id

    if task_type in [
        TaskType.CODING,
        TaskType.DATA_ANALYSIS,
        TaskType.CALCULATION,
    ]:
        model_id = "coder"
        update_model_status("coder", "active")
        return model_id

    if task_type in [
        TaskType.RAG_QA,
        TaskType.CORRESPONDENCE_SEARCH,
        TaskType.DOCUMENT_GENERATION,
        TaskType.PRESENTATION_GENERATION,
        TaskType.SPREADSHEET_WORK,
        TaskType.GENERAL_QA,
        TaskType.ITERATIVE_REVIEW,
    ]:
        model_id = "general"
        update_model_status("general", "active")
        return model_id

    if task_type == TaskType.MULTIMODAL_ANALYSIS:
        model_id = "vision"
        update_model_status("vision", "active")
        return model_id

    model_id = "general"
    update_model_status("general", "active")
    return model_id


def get_model_capabilities(model_id: str) -> list:
    model = model_registry.get(model_id)
    if model:
        return model.get("capabilities", [])
    return []
