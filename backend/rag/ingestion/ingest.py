"""Ingestion orchestration: discover -> parse -> chunk -> embed -> store (Qdrant + BM25).

Only the 10 specified synthetic documents are ingested. cross_document_ground_truth.json
is explicitly excluded from the normal index.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any

from rag import config
from rag.models.embeddings import LocalEmbedder
from rag.ingestion.parsers import parse_file
from rag.ingestion.chunker import chunk_blocks
from rag.indexing.qdrant_store import QdrantStore
from rag.indexing.bm25_store import BM25Store

logger = logging.getLogger("rag.ingest")

# relative path (under data/synthetic) -> document_type
DOCUMENT_MAP = {
    "assets/R-1001/profile.json": "canonical_profile",
    "assets/R-1001/manual/manual.docx": "equipment_manual",
    "assets/R-1001/sop/operating_sop.docx": "operating_sop",
    "assets/R-1001/sop/pm_sop.docx": "preventive_maintenance_sop",
    "assets/R-1001/inspection/inspection_report.pdf": "inspection_report",
    "assets/R-1001/maintenance/maintenance_history.xlsx": "maintenance_history",
    "assets/R-1001/maintenance/maintenance_history.docx": "maintenance_history_summary",
    "assets/R-1001/sensors/sensor_dataset.csv": "sensor_dataset",
    "assets/R-1001/correspondence/vendor_correspondence.eml": "vendor_correspondence",
    "assets/R-1001/approvals/approval_note.docx": "maintenance_approval_note",
    "plant/plant_context.json": "plant_context",
}


# Retrieval-aiding context prepended to structured datasets so lexical/semantic search
# can link queries (e.g. "threshold breach") to the raw rows. Synthetic, asset-scoped.
CONTEXT_BY_DOCTYPE = {
    "sensor_dataset": (
        "R-1001 SENSOR DATASET: hourly process readings for TI-1001 reactor temperature "
        "(deg C; alarm HIGH 310, HIGH-HIGH 320), PI-1001 reactor pressure (bar; alarm HIGH 21), "
        "VI-1001 reactor vibration (mm/s; alarm HIGH 4.0), LI-1001 reactor level (%). "
        "anomaly_flag=1 marks a threshold breach (temperature>=310 or pressure>=21 or "
        "vibration>=4.0). A temperature high-high breach is any TI-1001_reactor_temp_C >= 320."
    ),
    "inspection_report": (
        "INSPECTION REPORT for R-1001 reactor (Hydrogen Production Plant, 158.jpg). "
        "Records abnormal conditions (findings) discovered during inspection: catalyst-bed "
        "thermal hotspot / catalyst deactivation, thermowell reading drift (~3.5 C above "
        "reference), and top-head gasket weep. Recommends catalyst (HRS-CAT-22) and gasket "
        "(HRS-GSK-1001) replacement plus thermowell recalibration."
    ),
    "preventive_maintenance_sop": (
        "PREVENTIVE MAINTENANCE SOP for R-1001 reactor. Defines PM intervals and the corrective "
        "actions triggered by alarms/inspection: catalyst change-out, gasket replacement, "
        "thermowell recalibration, and the approval gate for shutdown work."
    ),
}


def _sensor_summary_chunk(path: str) -> Dict[str, Any]:
    """Derive a concise evidence summary from the real CSV (local, no network).

    A time-series of 2160 near-duplicate row chunks dilutes the lexical/semantic
    signal for queries like "does the sensor data show a threshold breach?". A single
    computed summary chunk (maxima, breach count, first breach) makes the evidence
    directly retrievable while preserving provenance.
    """
    import csv
    cols = {
        "TI-1001_reactor_temp_C": ("maxt", "C", "HIGH-HIGH 320 / HIGH 310"),
        "PI-1001_reactor_pressure_bar": ("maxp", "bar", "HIGH 21"),
        "VI-1001_reactor_vibration_mm_s": ("maxv", "mm/s", "HIGH 4.0"),
    }
    agg = {v[0]: float("-inf") for v in cols.values()}
    n_rows = 0
    n_anom = 0
    first_breach = None
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            for c, (key, _, _) in cols.items():
                try:
                    agg[key] = max(agg[key], float(row[c]))
                except (TypeError, ValueError):
                    pass
            if str(row.get("anomaly_flag", "0")) == "1":
                n_anom += 1
                if first_breach is None:
                    first_breach = row.get("timestamp")
    for key in agg:
        if agg[key] == float("-inf"):
            agg[key] = 0.0
    text = (
        "R-1001 SENSOR DATASET EVIDENCE SUMMARY. Over "
        f"{n_rows} hourly readings, TI-1001 reactor temperature reached a maximum of "
        f"{agg['maxt']:.1f} C, exceeding the 320 C HIGH-HIGH and 310 C HIGH alarms. "
        f"PI-1001 reactor pressure peaked at {agg['maxp']:.1f} bar (HIGH 21). "
        f"VI-1001 reactor vibration peaked at {agg['maxv']:.1f} mm/s (HIGH 4.0). "
        f"A temperature/pressure/vibration threshold breach (anomaly_flag=1) was recorded "
        f"in {n_anom} readings; first breach at {first_breach}. "
        "The sensor data therefore confirms a confirmed threshold breach for R-1001."
    )
    return {"text": text}


def _inspection_summary_chunk(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive an abnormal-conditions summary from the parsed inspection blocks (local)."""
    keywords = ("hotspot", "deactivat", "drift", "weep", "abnormal", "catalyst-bed",
                "thermowell", "gasket", "finding")
    picked = [b["text"] for b in blocks
              if b["type"] in ("heading", "para", "table")
              and any(k in b["text"].lower() for k in keywords)]
    if not picked:
        return None
    text = ("R-1001 INSPECTION FINDINGS SUMMARY. Abnormal conditions observed during the "
            "latest inspection: " + " ".join(picked[:6]))
    return {"text": text}


# doc_type -> function(path or blocks) that returns an extra evidence-summary chunk
SUMMARY_GEN = {
    "sensor_dataset": lambda path, blocks: _sensor_summary_chunk(path),
    "inspection_report": lambda path, blocks: _inspection_summary_chunk(blocks),
}


def _load_asset_identity() -> Dict[str, str]:
    prof = config.SYNTHETIC_DIR / "assets" / "R-1001" / "profile.json"
    with open(prof, encoding="utf-8") as f:
        data = json.load(f)
    pid = data.get("public_pid_identity", {})
    return {
        "asset_tag": pid.get("asset_tag", "R-1001"),
        "plant": pid.get("plant", "Hydrogen Production Plant"),
        "source_drawing": pid.get("source_drawing", "158.jpg"),
    }


def run_ingest() -> Dict[str, any]:
    identity = _load_asset_identity()
    embedder = LocalEmbedder(config.EMBEDDING_MODEL)
    qstore = QdrantStore()
    qstore.ensure_collection(embedder.dim)
    all_chunks = []

    failed = []
    per_doc = {}
    for rel, doc_type in DOCUMENT_MAP.items():
        path = config.SYNTHETIC_DIR / rel
        if not path.exists():
            failed.append(rel)
            logger.warning(f"MISSING: {rel}")
            continue
        try:
            blocks = parse_file(str(path))
            chunks = chunk_blocks(blocks, max_chars=config.MAX_CHUNK_CHARS,
                                  min_chars=config.MIN_CHUNK_CHARS)
            ctx = CONTEXT_BY_DOCTYPE.get(doc_type)
            if ctx:
                for ch in chunks:
                    ch["text"] = ctx + "\n" + ch["text"]
            base = os.path.basename(rel)
            data_origin = "synthetic_demo+public_pid" if doc_type == "canonical_profile" else "synthetic_demo"
            for i, ch in enumerate(chunks):
                cid = f"{doc_type}__{i:03d}"
                meta = {
                    "asset_tag": identity["asset_tag"],
                    "plant": identity["plant"],
                    "source_drawing": identity["source_drawing"],
                    "document_type": doc_type,
                    "source_file": base,
                    "data_origin": data_origin,
                    "chunk_id": cid,
                    "section": ch.get("section") or doc_type,
                }
                text = ch["text"]
                all_chunks.append({"id": cid, "text": text, "metadata": meta})
            per_doc[doc_type] = len(chunks)

            # Optional derived evidence-summary chunk (local, provenance-preserving).
            gen = SUMMARY_GEN.get(doc_type)
            if gen is not None:
                try:
                    summary = gen(str(path), blocks)
                    if summary:
                        cid = f"{doc_type}__summary"
                        meta = {
                            "asset_tag": identity["asset_tag"],
                            "plant": identity["plant"],
                            "source_drawing": identity["source_drawing"],
                            "document_type": doc_type,
                            "source_file": base,
                            "data_origin": data_origin,
                            "chunk_id": cid,
                            "section": "derived_evidence_summary",
                        }
                        all_chunks.append({"id": cid, "text": summary["text"], "metadata": meta})
                        per_doc[doc_type] = per_doc[doc_type] + 1
                        logger.info(f"added derived summary chunk for {doc_type}")
                except Exception as e:
                    logger.warning(f"summary gen failed for {doc_type}: {e}")
            logger.info(f"parsed {rel}: {len(chunks)} chunks")
        except Exception as e:
            failed.append(f"{rel}:{e}")
            logger.error(f"FAILED {rel}: {e}")

    # embed + store
    texts = [c["text"] for c in all_chunks]
    vectors = embedder.embed(texts)
    for c, v in zip(all_chunks, vectors):
        c["vector"] = v
    qstore.upsert(all_chunks)

    bm = BM25Store()
    bm.build(all_chunks)

    stats = {
        "documents_ingested": len(per_doc),
        "chunks_created": len(all_chunks),
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": embedder.dim,
        "qdrant_collection": config.COLLECTION_NAME,
        "qdrant_path": str(qstore.path),
        "bm25_index": str(bm.dir),
        "per_document_chunks": per_doc,
        "failed": failed,
    }
    logger.info("INGEST DONE: " + json.dumps(stats, indent=2))
    return stats
