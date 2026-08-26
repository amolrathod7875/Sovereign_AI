import logging
from typing import List, Dict, Any, Optional
import numpy as np

from app.storage.qdrant import search_chunks as qdrant_search

logger = logging.getLogger(__name__)


class DenseRetriever:
    """
    Dense retrieval using embeddings.
    """

    def __init__(self, model_endpoint: str = None):
        self.model_endpoint = model_endpoint
        self.embedding_dim = 1024

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts.
        In production, this calls the local embedding model via vLLM.
        For now, returns mock embeddings.
        """
        return [self._mock_embedding(text) for text in texts]

    def _mock_embedding(self, text: str) -> List[float]:
        """
        Generate a mock embedding vector.
        In production, this is replaced by actual model inference.
        """
        np.random.seed(hash(text) % (2**32))
        vec = np.random.randn(self.embedding_dim)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        return vec.tolist()

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using dense retrieval.
        """
        query_vector = await self.embed([query])
        results = await qdrant_search(query_vector[0], top_k=top_k)

        for result in results:
            result["source"] = "dense"
            result["score"] = float(result.get("score", 0))

        return results


dense_retriever = DenseRetriever()
