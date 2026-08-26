import logging
from typing import Dict, Any, List, Optional
import hashlib

from app.rag.parser import (
    parse_document,
    parse_pdf,
    parse_docx,
    parse_spreadsheet,
    parse_text,
)
from app.rag.ocr import detect_scanned_pages, perform_ocr
from app.rag.chunker import chunk_text

logger = logging.getLogger(__name__)


async def ingest_document_pipeline(document_id: str) -> Dict[str, Any]:
    """
    Complete document ingestion pipeline:
    1. Parse document (PyMuPDF for PDF, native for DOCX/XLSX)
    2. Detect if OCR is needed (scanned pages)
    3. OCR if needed (PaddleOCR)
    4. Structure-aware chunking
    5. Generate dense embeddings
    6. Generate BM25 tokens
    7. Index in Qdrant

    Args:
        document_id: ID of the uploaded document

    Returns:
        Ingestion result with stats
    """
    from app.storage.postgres import get_document_by_id

    doc = await get_document_by_id(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    logger.info(f"Starting ingestion for document: {doc.filename}")

    stages = {
        "parsing": 0,
        "ocr": 0,
        "chunking": 0,
        "embedding": 0,
        "indexing": 0,
    }

    try:
        stages["parsing"] = 1
        text_content = await parse_document(document_id, doc.filename)

        stages["parsing"] = 2
        logger.info(f"Parsed document, extracted {len(text_content)} characters")

        needs_ocr = await detect_scanned_pages(document_id)
        if needs_ocr:
            stages["ocr"] = 1
            text_content = await perform_ocr(document_id)
            stages["ocr"] = 2
            logger.info("OCR completed")

        stages["chunking"] = 1
        chunks = await chunk_text(text_content, doc)
        stages["chunking"] = 2
        logger.info(f"Created {len(chunks)} chunks")

        stages["embedding"] = 1
        await generate_embeddings(document_id, chunks)
        stages["embedding"] = 2
        logger.info("Embeddings generated")

        stages["indexing"] = 1
        await index_chunks(document_id, chunks)
        stages["indexing"] = 2
        logger.info("Chunks indexed in Qdrant")

        return {
            "document_id": document_id,
            "status": "completed",
            "stages": stages,
            "chunks": len(chunks),
            "characters": len(text_content),
        }

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        return {
            "document_id": document_id,
            "status": "failed",
            "error": str(e),
            "stages": stages,
        }


async def generate_embeddings(document_id: str, chunks: List[Dict[str, Any]]):
    """
    Generate embeddings for document chunks.
    Uses mock embeddings for now - replace with actual model.
    """
    from app.rag.dense import dense_retriever

    texts = [chunk["text"] for chunk in chunks]
    embeddings = await dense_retriever.embed(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding


async def index_chunks(document_id: str, chunks: List[Dict[str, Any]]):
    """
    Index chunks in Qdrant.
    """
    from app.storage.qdrant import insert_chunk

    for chunk in chunks:
        await insert_chunk(
            document_id=document_id,
            chunk_id=chunk["chunk_id"],
            text=chunk["text"],
            vector=chunk.get("embedding", [0] * 1024),
            metadata=chunk.get("metadata", {}),
        )
