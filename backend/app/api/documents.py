"""Document upload / registry surface.

Phase 6 integration notes
-------------------------
* ``POST /upload`` now returns ``stored_path`` plus honest per-format capability
  flags. The frontend needs ``stored_path`` because the authoritative vision and
  agent endpoints take a LOCAL ``file_path`` / ``image_path``; the file never
  leaves the machine.
* Supported formats are reported from the authoritative components themselves —
  ``rag.ingestion.parsers`` (text/knowledge parsing) and
  ``agent.config.SUPPORTED_VISION_EXT`` (vision) — instead of a hard-coded list,
  so the UI cannot claim support the backend does not have.
* ``POST /ingest`` and the registry reads still require PostgreSQL; when it is not
  running the failure is reported precisely (503 + reason) rather than as a
  generic error.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import hashlib
import logging
import uuid
import os
import aiofiles

from app.config import settings
from app.schemas import DocumentUploadResponse, DocumentResponse

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR)

# Formats the authoritative knowledge parsers accept (rag/ingestion/parsers.py).
PARSE_EXT = {".docx", ".pdf", ".xlsx", ".csv", ".json", ".eml"}


def _vision_ext() -> set:
    try:
        from agent.config import SUPPORTED_VISION_EXT

        return set(SUPPORTED_VISION_EXT)
    except Exception:  # pragma: no cover - vision package always present in-repo
        return set()


@router.get("/formats")
async def supported_formats():
    """Report the formats the BACKEND actually supports (no invented formats)."""
    vision = sorted(_vision_ext())
    return {
        "parse": sorted(PARSE_EXT),
        "vision": vision,
        "accept": sorted(PARSE_EXT | set(vision)),
        "max_file_mb": settings.MAX_FILE_MB,
        "upload_dir": UPLOAD_DIR,
    }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename supplied")
    if file.size and file.size > settings.MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {settings.MAX_FILE_MB}MB)",
        )

    file_extension = os.path.splitext(file.filename)[1].lower()
    vision_ext = _vision_ext()
    if file_extension not in (PARSE_EXT | vision_ext):
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{file_extension or '(none)'}'. This backend "
                f"supports {sorted(PARSE_EXT | vision_ext)}."
            ),
        )

    document_id = str(uuid.uuid4())
    stored_filename = f"{document_id}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    checksum = hashlib.sha256(content).hexdigest()

    try:
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not store upload in {UPLOAD_DIR}: {e}",
        )

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        size=len(content),
        checksum=checksum,
        stored_path=os.path.abspath(file_path),
        parse_supported=file_extension in PARSE_EXT,
        vision_supported=file_extension in vision_ext,
    )


@router.post("/ingest")
async def ingest_document(document_id: str):
    from app.rag.ingest import ingest_document_pipeline
    from app.rag.correspondence import ingest_correspondence_pipeline
    from app.storage.postgres import get_document_by_id, engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Document registry unavailable: PostgreSQL is not configured.",
        )

    try:
        doc = await get_document_by_id(document_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document registry unavailable: PostgreSQL is not reachable "
                f"({type(e).__name__}). The local knowledge index built by "
                "'python -m rag.run_ingest' does not require it."
            ),
        )

    filename = doc.filename if doc else f"{document_id}"
    ext = filename.lower().split(".")[-1]
    is_correspondence = ext in ["eml", "msg", "txt", "md"] or (
        doc is not None and doc.doc_type == "correspondence"
    )

    try:
        if is_correspondence:
            return await ingest_correspondence_pipeline(document_id)
        return await ingest_document_pipeline(document_id)
    except Exception as e:
        logger.error("ingest failed for %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail=f"ingestion failed: {e}")


@router.get("")
async def list_documents() -> List[DocumentResponse]:
    from app.storage.postgres import get_all_documents, engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Document registry unavailable: PostgreSQL is not configured.",
        )
    try:
        return await get_all_documents()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document registry unavailable: PostgreSQL is not reachable "
                f"({type(e).__name__})."
            ),
        )


@router.get("/{document_id}")
async def get_document(document_id: str) -> DocumentResponse:
    from app.storage.postgres import get_document_by_id, engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Document registry unavailable: PostgreSQL is not configured.",
        )
    try:
        doc = await get_document_by_id(document_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document registry unavailable: PostgreSQL is not reachable "
                f"({type(e).__name__})."
            ),
        )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    from app.storage.postgres import delete_document, engine

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Document registry unavailable: PostgreSQL is not configured.",
        )
    try:
        await delete_document(document_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document registry unavailable: PostgreSQL is not reachable "
                f"({type(e).__name__})."
            ),
        )
    return {"status": "deleted", "document_id": document_id}
