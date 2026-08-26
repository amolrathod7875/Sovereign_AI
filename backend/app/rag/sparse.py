import logging
from typing import List, Dict, Any
import re
from collections import Counter

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    Sparse retrieval using BM25 algorithm.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: Dict[str, List[str]] = {}
        self.avgdl = 0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.N = 0

    def index_document(self, doc_id: str, text: str):
        """
        Index a document for BM25 retrieval.
        """
        words = self._tokenize(text)
        self.documents[doc_id] = words
        self.N += 1

        for word in set(words):
            self.doc_freqs[word] = self.doc_freqs.get(word, 0) + 1

        self._compute_idf()
        self.avgdl = sum(len(doc) for doc in self.documents.values()) / max(self.N, 1)

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization.
        """
        text = text.lower()
        words = re.findall(r'\w+', text)
        return [w for w in words if len(w) > 2]

    def _compute_idf(self):
        """
        Compute IDF values for all indexed terms.
        """
        for word, df in self.doc_freqs.items():
            self.idf[word] = max(
                0, 
                0.5 * 0.5 * (self.N - df + 0.5) / (df + 0.5) / self.N
            )

    def _score_bm25(self, query_words: List[str], doc_words: List[str]) -> float:
        """
        Compute BM25 score for a document.
        """
        doc_len = len(doc_words)
        doc_freqs = Counter(doc_words)

        score = 0.0
        for word in query_words:
            if word not in self.idf:
                continue

            tf = doc_freqs.get(word, 0)
            idf = self.idf[word]

            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avgdl, 1))

            score += idf * numerator / denominator

        return score

    def search(self, query: str, top_k: int = 5, document_chunks: List[Dict] = None) -> List[Dict[str, Any]]:
        """
        Search for documents matching the query.
        """
        query_words = self._tokenize(query)
        if not query_words:
            return []

        if document_chunks:
            for chunk in document_chunks:
                self.index_document(chunk["chunk_id"], chunk["text"])

        scores = []
        for doc_id, doc_words in self.documents.items():
            score = self._score_BM25(query_words, doc_words)
            scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, score in scores[:top_k]:
            chunk = next((c for c in document_chunks if c["chunk_id"] == doc_id), None) if document_chunks else None
            if chunk:
                results.append({
                    "chunk_id": doc_id,
                    "text": chunk.get("text", ""),
                    "document": chunk.get("document", "unknown"),
                    "page": chunk.get("page"),
                    "score": float(score),
                    "source": "bm25",
                })

        return results


bm25_retriever = BM25Retriever()
