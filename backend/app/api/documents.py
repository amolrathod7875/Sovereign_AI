from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import hashlib
import uuid
import os
import aiofiles

from app.config import settings
from app.schemas import DocumentUploadResponse, DocumentResponse

router = APIRouter()

UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR)


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if file.size and file.size > settings.MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.MAX_FILE_MB}MB)")

    document_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    stored_filename = f"{document_id}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        size=len(content),
        checksum=checksum,
    )


@router.post("/ingest")
async def ingest_document(document_id: str):
    from app.rag.ingest import ingest_document_pipeline
    from app.rag.correspondence import ingest_correspondence_pipeline
    from app.storage.postgres import get_document_by_id

    try:
        doc = await get_document_by_id(document_id)
        filename = doc.filename if doc else f"{document_id}"

        ext = filename.lower().split(".")[-1]
        is_correspondence = ext in ["eml", "msg", "txt", "md"] or (
            doc is not None and doc.doc_type == "correspondence"
        )

        if is_correspondence:
            result = await ingest_correspondence_pipeline(document_id)
        else:
            result = await ingest_document_pipeline(document_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_documents() -> List[DocumentResponse]:
    from app.storage.postgres import get_all_documents

    docs = await get_all_documents()
    return docs


@router.get("/{document_id}")
async def get_document(document_id: str) -> DocumentResponse:
    from app.storage.postgres import get_document_by_id

    doc = await get_document_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    from app.storage.postgres import delete_document

    await delete_document(document_id)
    return {"status": "deleted", "document_id": document_id}
