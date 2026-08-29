"""Tool: read_document

Reads PDF / DOCX / XLSX / CSV / EML / JSON and returns extracted content while
preserving source metadata. Reuses the existing Phase 3 block parsers so the
agent and the RAG index share one parsing implementation.
"""
import logging
import os
from typing import Dict, Any, List

from rag.ingestion.parsers import parse_file

logger = logging.getLogger(__name__)


def read_document(path: str) -> Dict[str, Any]:
    """Return extracted content for a supported file.

    Returns:
        {
          "source_file": str,
          "ext": str,
          "content": str,            # concatenated text (retrieval/extraction friendly)
          "blocks": List[Dict],      # structured blocks from the shared parser
          "num_blocks": int,
        }
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    blocks = parse_file(path)
    content = "\n".join(b.get("text", "") for b in blocks)
    return {
        "source_file": os.path.basename(path),
        "ext": os.path.splitext(path)[1].lower(),
        "content": content,
        "blocks": blocks,
        "num_blocks": len(blocks),
    }
