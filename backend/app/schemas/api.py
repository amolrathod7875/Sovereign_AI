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


class SystemStatus(BaseModel):
    sovereign: bool = True
    gpu: Optional[dict] = None
    services: dict
    uptime_seconds: int
    external_api_calls: int = 0


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


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    mime_type: str
    size: int
    checksum: str


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
