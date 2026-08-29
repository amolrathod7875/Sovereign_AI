"""Structure-aware chunking: keeps headings/sections and tables coherent.

Strategy:
- A heading starts a new section; subsequent paragraphs/rows are grouped under it.
- Tables become their own chunk (preserves tabular structure).
- Row-type blocks (XLSX/CSV) are batched until MAX_CHUNK_CHARS.
- Paragraphs are grouped until MAX_CHUNK_CHARS.
No arbitrary fixed-size splitting across section boundaries.
"""
from typing import List, Dict, Any


def chunk_blocks(blocks: List[Dict[str, Any]], max_chars: int = 1200,
                 min_chars: int = 80) -> List[Dict[str, Any]]:
    chunks = []
    section = None
    buf: List[str] = []

    def flush():
        text = "\n".join(buf).strip()
        if text and len(text) >= min_chars or (text and not buf):  # keep short tail too
            chunks.append({"section": section, "text": text})
        buf.clear()

    for b in blocks:
        t = b["type"]
        if t == "heading":
            flush()
            section = b["text"]
            buf.append(b["text"])
        elif t == "table":
            flush()
            chunks.append({"section": section, "text": b["text"]})
        else:
            line = b["text"]
            if buf and (sum(len(x) for x in buf) + len(line) + 1) > max_chars:
                flush()
                # continue same section
            buf.append(line)
    flush()
    return chunks
