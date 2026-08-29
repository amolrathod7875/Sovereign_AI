"""Local BM25 lexical index (bm25s), persisted to disk.

bm25s.BM25 returns positional indices, so we persist an ordered chunk-id list and a
corpus map to reconstruct hits and apply asset/document_type filters after retrieval.
"""
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

import bm25s

from rag import config

logger = logging.getLogger("rag.bm25_store")


class BM25Store:
    def __init__(self, path: Path = None):
        self.dir = Path(path or config.BM25_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "bm25_index"
        self.corpus_path = self.dir / "corpus.json"
        self._retriever = None
        self._order: List[str] = []
        self._chunks: Dict[str, Dict[str, Any]] = {}

    def build(self, chunks: List[Dict[str, Any]]):
        """chunks: list of {chunk_id, text, metadata}."""
        self._order = [c["id"] for c in chunks]
        self._chunks = {c["id"]: {"text": c["text"], "metadata": c["metadata"]} for c in chunks}
        texts = [self._chunks[i]["text"] for i in self._order]
        tokenized = bm25s.tokenize(texts, stopwords="en")
        retriever = bm25s.BM25()
        retriever.index(tokenized)
        retriever.save(str(self.index_path))
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump({"order": self._order, "chunks": self._chunks}, f, ensure_ascii=False, indent=2)
        logger.info(f"BM25 index built: {len(self._order)} chunks -> {self.index_path}")

    def load(self):
        if not self.index_path.exists():
            raise FileNotFoundError("BM25 index not found; run ingestion first.")
        self._retriever = bm25s.BM25.load(str(self.index_path))
        with open(self.corpus_path, encoding="utf-8") as f:
            data = json.load(f)
        self._order = data["order"]
        self._chunks = data["chunks"]
        logger.info(f"BM25 index loaded: {len(self._order)} chunks")

    def search(self, query: str, top_k: int = 8,
               asset_tag: str = None, document_type: str = None) -> List[Dict[str, Any]]:
        if self._retriever is None:
            self.load()
        q = bm25s.tokenize(query, stopwords="en")
        doc_ids, scores = self._retriever.retrieve(q, k=top_k * 4)
        results = []
        for dids, scs in zip(doc_ids, scores):
            for pos, s in zip(dids, scs):
                cid = self._order[int(pos)]
                meta = self._chunks[cid]["metadata"]
                if asset_tag and meta.get("asset_tag") != asset_tag:
                    continue
                if document_type and meta.get("document_type") != document_type:
                    continue
                results.append({
                    "chunk_id": cid, "score": float(s),
                    "text": self._chunks[cid]["text"], "metadata": meta,
                })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
