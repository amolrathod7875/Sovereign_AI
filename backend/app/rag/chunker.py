import logging
import uuid
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


async def chunk_text(text: str, doc, chunk_size: int = 512, overlap: int = 64) -> List[Dict[str, Any]]:
    """
    Create structure-aware chunks from text.
    """
    chunks = []

    lines = text.split("\n")
    current_chunk = []
    current_size = 0

    for line in lines:
        line_size = len(line.split())

        if current_size + line_size > chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)

            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": chunk_text,
                "metadata": {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "chunk_index": len(chunks),
                },
            })

            overlap_lines = current_chunk[-overlap // 10:] if len(current_chunk) > overlap // 10 else []
            current_chunk = overlap_lines + [line]
            current_size = sum(len(l.split()) for l in current_chunk)
        else:
            current_chunk.append(line)
            current_size += line_size

    if current_chunk:
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "text": " ".join(current_chunk),
            "metadata": {
                "document_id": doc.id,
                "filename": doc.filename,
                "chunk_index": len(chunks),
            },
        })

    return chunks
