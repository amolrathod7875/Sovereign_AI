from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class SourceInfo(BaseModel):
    filename: str
    relative_path: str
    type: str = "local_project"

class FileInfo(BaseModel):
    mime_type: str
    size_bytes: int
    sha256: str

class Metadata(BaseModel):
    title: Optional[str] = None
    classification: Optional[str] = None
    author: Optional[str] = None
    created_date: Optional[str] = None

class ContentElement(BaseModel):
    type: str  # "heading", "paragraph", "table", "record"
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None # For structured records

class PageContent(BaseModel):
    page_number: int
    elements: List[ContentElement]

class DocumentContent(BaseModel):
    pages: Optional[List[PageContent]] = None
    records: Optional[List[Dict[str, Any]]] = None # For CSV/JSON rows without pages
    raw_text: Optional[str] = None

class IngestionInfo(BaseModel):
    parser: str
    pipeline_version: str = "0.1.0"
    processed_at: str
    status: str

class Document(BaseModel):
    document_id: str
    project_id: str
    source: SourceInfo
    file: FileInfo
    metadata: Metadata
    content: DocumentContent
    ingestion: IngestionInfo
