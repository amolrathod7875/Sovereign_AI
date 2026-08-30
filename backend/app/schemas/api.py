from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class TaskType(str, Enum):
    GENERAL_QA = "GENERAL_QA"
    RAG_QA = "RAG_QA"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    MULTIMODAL_ANALYSIS = "MULTIMODAL_ANALYSIS"
    CODING = "CODING"
    DATA_ANALYSIS = "DATA_ANALYSIS"
    DOCUMENT_GENERATION = "DOCUMENT_GENERATION"
    PRESENTATION_GENERATION = "PRESENTATION_GENERATION"
    SPREADSHEET_WORK = "SPREADSHEET_WORK"
    CORRESPONDENCE_SEARCH = "CORRESPONDENCE_SEARCH"
    ITERATIVE_REVIEW = "ITERATIVE_REVIEW"
    CALCULATION = "CALCULATION"


class AgentRunRequest(BaseModel):
    message: str
    attachments: Optional[List[str]] = []
    mode: str = "sovereign"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ExecutionStep(BaseModel):
    step_index: int
    action: str
    status: StepStatus
    model: Optional[str] = None
    tool: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Optional[dict] = None


class ExecutionResponse(BaseModel):
    id: str
    task_type: TaskType
    status: ExecutionStatus
    selected_model: Optional[str] = None
    steps: List[ExecutionStep]
    artifacts: List[str] = []
    errors: List[str] = []
    external_calls: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    attachments: Optional[List[str]] = []
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: ChatMessage
    sources: List[dict] = []
    artifact_id: Optional[str] = None


class ComponentStatus(BaseModel):
    """Honest, probed status of one authoritative platform component.

    ``status`` is one of ONLINE / OFFLINE / UNAVAILABLE / NOT CONFIGURED and is
    always derived from a real probe (see ``app.api.system``), never assumed.
    """

    id: str
    name: str
    status: str
    detail: str = ""
    endpoint: Optional[str] = None
    local: bool = True


class SystemStatus(BaseModel):
    sovereign: bool = True
    gpu: Optional[dict] = None
    services: dict
    components: List[ComponentStatus] = []
    uptime_seconds: int
    external_api_calls: int = 0
    blocked_connections: int = 0


class NetworkEvent(BaseModel):
    id: str
    timestamp: datetime
    destination_host: str
    destination_port: int
    action: str
    execution_id: Optional[str] = None


class ModelInfo(BaseModel):
    id: str
    name: str
    endpoint: str
    capabilities: List[str]
    context_length: int
    status: str
    vram_gb: Optional[float] = None
    local: bool = True
    modalities: List[str] = ["text"]


class RoutingRequest(BaseModel):
    """Structured task description handed to the unified local model router.

    Either ``task`` (free text) is supplied and classified, or the task
    characteristics are provided explicitly. ``image_path`` / ``has_image`` mark a
    multimodal input; explicit booleans override classification when known.
    """

    task: str = ""
    task_type: Optional[str] = None
    modality: Optional[str] = None          # "text" | "image" | "image+text"
    has_image: bool = False
    image_path: Optional[str] = None
    requires_code: Optional[bool] = None
    requires_vision: Optional[bool] = None
    requires_rag: Optional[bool] = None
    requires_tools: Optional[bool] = None
    complexity: Optional[str] = None         # "low" | "medium" | "high"
    asset_tag: Optional[str] = None
    local_only: bool = True


class RoutingDecision(BaseModel):
    """Explainable, capability-based routing result.

    ``selected_model`` is the primary model; ``models_required`` lists every local
    model a complex task needs (e.g. vision + general for multimodal). ``external_calls``
    is always 0 for a Sovereign-AI production routing decision.
    """

    task_type: str
    modality: str
    selected_model: str
    models_required: List[str] = []
    requires_rag: bool = False
    requires_tools: bool = False
    confidence: float = 0.0
    reason: str = ""
    capabilities: List[str] = []
    local_only: bool = True
    all_local: bool = True
    external_calls: int = 0


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    size: int
    checksum: str
    # Absolute path of the stored file on the local machine. Required so the client
    # can hand the SAME local file to the existing vision (`/api/vision/analyze`)
    # and agent (`/api/agent/run`) endpoints, which take a local `file_path` /
    # `image_path`. It never leaves the machine.
    stored_path: Optional[str] = None
    # Whether the authoritative parsers/vision tool accept this extension.
    parse_supported: bool = False
    vision_supported: bool = False


class ArtifactInfo(BaseModel):
    """A file already produced by the authoritative agent/tools.

    The frontend only lists and downloads these; artifact *generation* stays in
    ``agent/tools`` and ``app/tools``.
    """

    artifact_id: str
    filename: str
    kind: str
    size: int
    mime_type: str
    modified_at: datetime
    run_id: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    status: str
    doc_type: str
    pages: Optional[int] = None
    chunks: Optional[int] = None
    created_at: datetime
