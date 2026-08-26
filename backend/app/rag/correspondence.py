import logging
import email
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from email.parser import Parser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
import uuid

logger = logging.getLogger(__name__)


class CorrespondenceMetadata:
    def __init__(
        self,
        sender: str,
        recipients: List[str],
        date: Optional[datetime],
        subject: str,
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ):
        self.sender = sender
        self.recipients = recipients
        self.date = date
        self.subject = subject
        self.thread_id = thread_id
        self.message_id = message_id
        self.in_reply_to = in_reply_to

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "recipients": self.recipients,
            "date": self.date.isoformat() if self.date else None,
            "subject": self.subject,
            "thread_id": self.thread_id,
            "message_id": self.message_id,
            "in_reply_to": self.in_reply_to,
        }


async def parse_eml_file(document_id: str, filename: str) -> Tuple[str, CorrespondenceMetadata]:
    """
    Parse an .eml email file and extract metadata and body.

    Args:
        document_id: The document ID
        filename: Original filename

    Returns:
        Tuple of (body_text, metadata)
    """
    try:
        from app.config import settings
        import os

        file_path = f"{settings.UPLOAD_DIR}/{document_id}.eml"

        if not os.path.exists(file_path):
            file_path = f"{settings.UPLOAD_DIR}/{filename}"

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            msg = email.message_from_file(f, policy=default)

        metadata = extract_email_metadata(msg)
        body = extract_email_body(msg)

        logger.info(f"Parsed email from {metadata.sender}, subject: {metadata.subject}")
        return body, metadata

    except Exception as e:
        logger.error(f"EML parsing error: {e}")
        return "", CorrespondenceMetadata(
            sender="unknown",
            recipients=[],
            date=None,
            subject="Unknown",
        )


async def parse_msg_file(document_id: str, filename: str) -> Tuple[str, CorrespondenceMetadata]:
    """
    Parse a .msg Outlook file.
    Requires python-docx or extract_msg library.

    Args:
        document_id: The document ID
        filename: Original filename

    Returns:
        Tuple of (body_text, metadata)
    """
    try:
        import extract_msg

        from app.config import settings

        file_path = f"{settings.UPLOAD_DIR}/{document_id}.msg"

        if not os.path.exists(file_path):
            file_path = f"{settings.UPLOAD_DIR}/{filename}"

        msg = extract_msg.Message(file_path)

        metadata = CorrespondenceMetadata(
            sender=msg.sender,
            recipients=msg.recipients or [],
            date=msg.date if msg.date else None,
            subject=msg.subject or "Unknown",
            message_id=msg.message_id if hasattr(msg, "message_id") else None,
        )

        body = msg.body or ""

        msg.close()

        logger.info(f"Parsed MSG from {metadata.sender}, subject: {metadata.subject}")
        return body, metadata

    except ImportError:
        logger.warning("extract_msg not installed, MSG parsing unavailable")
        return "", CorrespondenceMetadata(
            sender="unknown",
            recipients=[],
            date=None,
            subject="Unknown",
        )
    except Exception as e:
        logger.error(f"MSG parsing error: {e}")
        return "", CorrespondenceMetadata(
            sender="unknown",
            recipients=[],
            date=None,
            subject="Unknown",
        )


async def parse_letter_file(document_id: str, filename: str) -> Tuple[str, CorrespondenceMetadata]:
    """
    Parse a plain text letter file with header lines.
    Expected format:
        From: Sender Name
        To: Recipient Name
        Date: YYYY-MM-DD
        Subject: Letter Subject

        Body text starts here...

    Args:
        document_id: The document ID
        filename: Original filename

    Returns:
        Tuple of (body_text, metadata)
    """
    try:
        from app.config import settings
        import os

        file_path = f"{settings.UPLOAD_DIR}/{document_id}.txt"

        if not os.path.exists(file_path):
            for ext in ["txt", "md"]:
                candidate = f"{settings.UPLOAD_DIR}/{document_id}.{ext}"
                if os.path.exists(candidate):
                    file_path = candidate
                    break

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        metadata = extract_letter_metadata(content)
        body = extract_letter_body(content)

        logger.info(f"Parsed letter from {metadata.sender} to {metadata.recipients}")
        return body, metadata

    except Exception as e:
        logger.error(f"Letter parsing error: {e}")
        return "", CorrespondenceMetadata(
            sender="unknown",
            recipients=[],
            date=None,
            subject="Unknown",
        )


def extract_email_metadata(msg: email.message.EmailMessage) -> CorrespondenceMetadata:
    """
    Extract metadata from an email message.
    """
    sender = ""
    sender_name, sender_email = parseaddr(msg.get("From", ""))
    sender = sender_email if sender_email else sender_name

    recipients = []
    for recipient in msg.get("To", "").split(","):
        _, email_addr = parseaddr(recipient.strip())
        if email_addr:
            recipients.append(email_addr)
        elif recipient.strip():
            recipients.append(recipient.strip())

    cc_recipients = []
    for cc in msg.get("Cc", "").split(","):
        _, email_addr = parseaddr(cc.strip())
        if email_addr:
            cc_recipients.append(email_addr)

    date_str = msg.get("Date", "")
    date = None
    if date_str:
        try:
            date = parsedate_to_datetime(date_str)
        except Exception:
            try:
                date = datetime.fromisoformat(date_str)
            except Exception:
                pass

    subject = msg.get("Subject", "Unknown")

    message_id = msg.get("Message-ID", None)
    in_reply_to = msg.get("In-Reply-To", None)

    thread_id = None
    references = msg.get("References", "")
    if references:
        thread_id = references.split()[0] if references else None
    elif in_reply_to:
        thread_id = in_reply_to

    return CorrespondenceMetadata(
        sender=sender,
        recipients=recipients,
        date=date,
        subject=subject,
        thread_id=thread_id,
        message_id=message_id,
        in_reply_to=in_reply_to,
    )


def extract_email_body(msg: email.message.EmailMessage) -> str:
    """
    Extract the body text from an email message, handling multipart messages.
    """
    body_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    text = part.get_payload(decode=True).decode(charset, errors="replace")
                    body_parts.append(text)
                except Exception:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            body_parts.append(msg.get_payload(decode=True).decode(charset, errors="replace"))
        except Exception:
            pass

    return "\n\n".join(body_parts)


def extract_letter_metadata(content: str) -> CorrespondenceMetadata:
    """
    Extract metadata from a letter's header lines.
    """
    sender = ""
    recipients: List[str] = []
    date = None
    subject = ""

    lines = content.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if line_stripped.startswith("From:"):
            sender = line_stripped[5:].strip()
        elif line_stripped.startswith("To:"):
            recipients = [r.strip() for r in line_stripped[3:].split(",")]
        elif line_stripped.startswith("Date:"):
            date_str = line_stripped[5:].strip()
            try:
                date = datetime.fromisoformat(date_str)
            except Exception:
                try:
                    date = parsedate_to_datetime(date_str)
                except Exception:
                    pass
        elif line_stripped.startswith("Subject:"):
            subject = line_stripped[8:].strip()
        elif line_stripped == "" and i > 0:
            body_start = i + 1
            break
        elif not line_stripped.startswith(("From:", "To:", "Date:", "Subject:")) and i > 3:
            body_start = 0
            break

    return CorrespondenceMetadata(
        sender=sender or "Unknown",
        recipients=recipients or ["Unknown"],
        date=date,
        subject=subject or "Letter",
    )


def extract_letter_body(content: str) -> str:
    """
    Extract body from a letter, skipping header lines.
    """
    lines = content.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped == "" and i > 0:
            body_start = i + 1
            break
        elif not line_stripped.startswith(("From:", "To:", "Date:", "Subject:")) and i > 3:
            body_start = 0
            break

    body_lines = lines[body_start:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    return "\n".join(body_lines)


async def parse_correspondence(document_id: str, filename: str) -> Tuple[str, CorrespondenceMetadata]:
    """
    Parse any correspondence file based on extension.

    Args:
        document_id: The document ID
        filename: Original filename

    Returns:
        Tuple of (body_text, metadata)
    """
    ext = filename.lower().split(".")[-1]

    if ext == "eml":
        return await parse_eml_file(document_id, filename)
    elif ext == "msg":
        return await parse_msg_file(document_id, filename)
    elif ext in ["txt", "md"]:
        return await parse_letter_file(document_id, filename)
    else:
        logger.warning(f"Unsupported correspondence format: {ext}")
        return "", CorrespondenceMetadata(
            sender="unknown",
            recipients=[],
            date=None,
            subject="Unknown",
        )


def chunk_correspondence(
    body: str,
    metadata: CorrespondenceMetadata,
    document_id: str,
    filename: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[Dict[str, Any]]:
    """
    Create structure-aware chunks from correspondence, preserving thread context.

    Args:
        body: The email/letter body text
        metadata: CorrespondenceMetadata object
        document_id: The document ID
        filename: Original filename
        chunk_size: Target chunk size in words
        overlap: Number of overlapping words between chunks

    Returns:
        List of chunk dictionaries
    """
    chunks = []
    lines = body.split("\n")
    current_chunk = []
    current_size = 0

    metadata_header = (
        f"[From: {metadata.sender} | "
        f"To: {', '.join(metadata.recipients)} | "
        f"Date: {metadata.date.strftime('%Y-%m-%d') if metadata.date else 'Unknown'} | "
        f"Subject: {metadata.subject}]"
    )

    for line in lines:
        line_size = len(line.split())

        if current_size + line_size > chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)

            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": f"{metadata_header}\n\n{chunk_text}",
                "metadata": {
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": len(chunks),
                    "doc_type": "correspondence",
                    "sender": metadata.sender,
                    "recipients": metadata.recipients,
                    "date": metadata.date.isoformat() if metadata.date else None,
                    "subject": metadata.subject,
                    "thread_id": metadata.thread_id,
                },
            })

            overlap_lines = current_chunk[-overlap // 10:] if len(current_chunk) > overlap // 10 else []
            current_chunk = overlap_lines + [line]
            current_size = sum(len(l.split()) for l in current_chunk)
        else:
            current_chunk.append(line)
            current_size += line_size

    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "text": f"{metadata_header}\n\n{chunk_text}",
            "metadata": {
                "document_id": document_id,
                "filename": filename,
                "chunk_index": len(chunks),
                "doc_type": "correspondence",
                "sender": metadata.sender,
                "recipients": metadata.recipients,
                "date": metadata.date.isoformat() if metadata.date else None,
                "subject": metadata.subject,
                "thread_id": metadata.thread_id,
            },
        })

    return chunks


async def ingest_correspondence_pipeline(document_id: str) -> Dict[str, Any]:
    """
    Complete correspondence ingestion pipeline:
    1. Parse correspondence (.eml, .msg, .txt)
    2. Extract metadata (headers, sender, recipient, date, thread)
    3. Structure-aware chunking
    4. Generate embeddings
    5. Index in Qdrant

    Args:
        document_id: ID of the uploaded correspondence

    Returns:
        Ingestion result with stats
    """
    from app.storage.postgres import get_document_by_id
    from app.rag.dense import dense_retriever
    from app.storage.qdrant import insert_chunk

    doc = await get_document_by_id(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    logger.info(f"Starting correspondence ingestion for: {doc.filename}")

    stages = {
        "parsing": 0,
        "chunking": 0,
        "embedding": 0,
        "indexing": 0,
    }

    try:
        stages["parsing"] = 1
        body, metadata = await parse_correspondence(document_id, doc.filename)
        stages["parsing"] = 2

        if not body:
            logger.warning(f"No body content extracted from {doc.filename}")
            return {
                "document_id": document_id,
                "status": "failed",
                "error": "No body content extracted",
                "stages": stages,
            }

        logger.info(f"Parsed correspondence, extracted {len(body)} characters")

        stages["chunking"] = 1
        chunks = chunk_correspondence(body, metadata, document_id, doc.filename)
        stages["chunking"] = 2
        logger.info(f"Created {len(chunks)} chunks")

        stages["embedding"] = 1
        texts = [chunk["text"] for chunk in chunks]
        embeddings = await dense_retriever.embed(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
        stages["embedding"] = 2

        stages["indexing"] = 1
        for chunk in chunks:
            await insert_chunk(
                document_id=document_id,
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                vector=chunk.get("embedding", [0] * 1024),
                metadata=chunk.get("metadata", {}),
            )
        stages["indexing"] = 2

        return {
            "document_id": document_id,
            "status": "completed",
            "stages": stages,
            "chunks": len(chunks),
            "characters": len(body),
            "metadata": metadata.to_dict(),
        }

    except Exception as e:
        logger.error(f"Correspondence ingestion error: {e}")
        return {
            "document_id": document_id,
            "status": "failed",
            "error": str(e),
            "stages": stages,
        }


async def search_correspondence(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Search correspondence using hybrid RAG.

    Args:
        query: Search query
        top_k: Number of results to return

    Returns:
        List of matching correspondence chunks
    """
    from app.rag.retrieval import hybrid_search

    results = await hybrid_search(query, top_k=top_k, doc_type_filter="correspondence")

    return results
