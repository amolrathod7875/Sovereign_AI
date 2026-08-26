import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    source_id: str
    document: str
    page: Optional[str]
    section: Optional[str]
    text: str
    score: float
    doc_type: str


class CitationFormatter:
    """
    Formats RAG retrieval results into citations for agent responses.
    """

    @staticmethod
    def format_citation(chunk: Dict[str, Any], score: float = 0.0) -> Citation:
        """
        Create a Citation from a RAG chunk result.

        Args:
            chunk: Chunk dictionary from retrieval
            score: Relevance score

        Returns:
            Citation object
        """
        metadata = chunk.get("metadata", {})
        doc_type = metadata.get("doc_type", "unknown")

        page = None
        if "page" in metadata:
            page = str(metadata["page"])
        elif "page_num" in metadata:
            page = str(metadata["page_num"])

        section = metadata.get("section") or metadata.get("chunk_index")

        if doc_type == "correspondence":
            source_id = f"{metadata.get('filename', 'unknown')}"
            if metadata.get("sender"):
                source_id += f" from {metadata['sender']}"
            document = source_id
        else:
            document = metadata.get("filename", "Unknown Document")
            if page:
                document += f" p.{page}"

        return Citation(
            source_id=metadata.get("document_id", ""),
            document=document,
            page=page,
            section=str(section) if section is not None else None,
            text=chunk.get("text", "")[:500],
            score=score,
            doc_type=doc_type,
        )

    @staticmethod
    def format_citations(chunks: List[Dict[str, Any]], scores: Optional[List[float]] = None) -> List[Citation]:
        """
        Create a list of Citations from RAG results.

        Args:
            chunks: List of chunks from retrieval
            scores: Optional list of relevance scores

        Returns:
            List of Citation objects
        """
        if scores is None:
            scores = [0.0] * len(chunks)

        citations = []
        for chunk, score in zip(chunks, scores):
            try:
                citation = CitationFormatter.format_citation(chunk, score)
                citations.append(citation)
            except Exception as e:
                logger.error(f"Error formatting citation: {e}")
                continue

        return citations

    @staticmethod
    def citation_to_dict(citation: Citation) -> Dict[str, Any]:
        """
        Convert a Citation to a dictionary.

        Args:
            citation: Citation object

        Returns:
            Dictionary representation
        """
        return {
            "source_id": citation.source_id,
            "document": citation.document,
            "page": citation.page,
            "section": citation.section,
            "text": citation.text,
            "score": citation.score,
            "doc_type": citation.doc_type,
        }

    @staticmethod
    def format_evidence_text(citations: List[Citation], max_length: int = 1000) -> str:
        """
        Format citations as evidence text for agent prompts.

        Args:
            citations: List of citations
            max_length: Maximum total length

        Returns:
            Formatted evidence string
        """
        evidence_parts = []
        current_length = 0

        for i, citation in enumerate(citations):
            part = f"[{i+1}] {citation.document}"

            if citation.section:
                part += f", section {citation.section}"

            if citation.doc_type == "correspondence":
                part += f"\n  {citation.text[:300]}..."
            else:
                part += f"\n  {citation.text[:300]}..."

            if current_length + len(part) > max_length:
                break

            evidence_parts.append(part)
            current_length += len(part)

        if not evidence_parts:
            return "No evidence retrieved."

        return "\n\n".join(evidence_parts)

    @staticmethod
    def format_source_list(citations: List[Citation]) -> str:
        """
        Format a numbered list of sources for citations.

        Args:
            citations: List of citations

        Returns:
            Formatted source list
        """
        if not citations:
            return "No sources."

        lines = []
        for i, citation in enumerate(citations):
            source = f"{i+1}. {citation.document}"
            if citation.page:
                source += f" (page {citation.page})"
            if citation.section:
                source += f", section {citation.section}"
            lines.append(source)

        return "\n".join(lines)


def create_citation_context(
    chunks: List[Dict[str, Any]],
    scores: Optional[List[float]] = None,
    max_citations: int = 5,
) -> Dict[str, Any]:
    """
    Create a complete citation context from RAG results.

    Args:
        chunks: List of chunks from retrieval
        scores: Optional relevance scores
        max_citations: Maximum number of citations to include

    Returns:
        Dictionary with formatted citations, evidence text, and source list
    """
    citations = CitationFormatter.format_citations(chunks[:max_citations], scores[:max_citations] if scores else None)

    return {
        "citations": [CitationFormatter.citation_to_dict(c) for c in citations],
        "evidence_text": CitationFormatter.format_evidence_text(citations),
        "source_list": CitationFormatter.format_source_list(citations),
        "count": len(citations),
    }
