import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


async def search_knowledge_base(
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Search the local knowledge base using hybrid RAG.
    """
    from app.rag import hybrid_search

    results = await hybrid_search(query, top_k=top_k)

    if document_ids:
        results = [r for r in results if r.get("document_id") in document_ids]

    return results


async def read_local_file(filepath: str) -> str:
    """
    Read a file from the local filesystem.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"File read error: {e}")
        return ""


async def write_local_file(filepath: str, content: str) -> bool:
    """
    Write content to a local file.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"File write error: {e}")
        return False
