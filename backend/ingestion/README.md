# Sovereign AI Workbench - Ingestion Subsystem

**Phase 1 + 1.5: Local Ingestion & Frontend**

This subsystem prepares validated, normalized local enterprise data for future RAG processing. It does not implement RAG, embeddings, vector search, LLMs, or agents.

## 1. What Phase 1 + 1.5 Does
This subsystem provides a standalone, air-gapped pipeline for discovering, hashing, deduplicating, parsing, and normalizing local enterprise documents into a structured JSON format. It includes a frontend for uploading files and folders and maintaining a local sync state.

## 2. Architecture
The ingestion pipeline is:
`DATA SOURCE → DISCOVERY → VALIDATION → SHA-256 → DEDUPLICATION / CHANGE DETECTION → PARSER ROUTING → EXTRACTION → NORMALIZATION → METADATA / PROVENANCE → PYDANTIC VALIDATION → LOCAL STORAGE → AUDIT MANIFEST`

## 3. Supported Input Types
- `.pdf`
- `.docx`, `.pptx`, `.xlsx`, `.csv`
- `.txt`, `.json`
- `.png`, `.jpg`, `.jpeg`, `.tiff`

## 4. Folder Upload Behaviour
Folders uploaded via the frontend or CLI retain their hierarchical structure. The system stages the files in `data/incoming/` before passing them to the ingestion pipeline.

## 5. Duplicate Behaviour
The system computes a SHA-256 hash of every file.
- **Exact Duplicate**: If the content hash is identical to a previously ingested file, it records a `DUPLICATE` event and skips parsing. It does not overwrite the canonical copy.
- **Same Content, Different Name**: Treated as a `DUPLICATE`.
- **Modified File**: If a previously synced file is modified (different hash), it is ingested as a new document, and a `MODIFIED` event is logged in the manifest linking the old and new document IDs.

## 6. Storage Structure
- `data/incoming/`: Temporary staging for uploads and syncs.
- `data/raw/`: Immutable copies of the original files.
- `data/processed/`: Normalized JSON documents adhering to Pydantic schemas.
- `data/failed/`: Corrupted or unparseable files, along with an `error.json` detailing the failure.
- `data/sync_state/`: Local folder synchronization states.
- `data/manifest.jsonl`: Audit history of all events (`INGESTED`, `DUPLICATE`, `FAILED`, `MODIFIED`, `DELETED`).

## 7. Parser Status
- **Apache Tika**: NOT IMPLEMENTED (Simulated)
- **Docling**: NOT IMPLEMENTED (Simulated via PyPDF)
- **Unstructured**: NOT IMPLEMENTED (Simulated)
- **OCR (Tesseract)**: NOT IMPLEMENTED (Simulated)
- **Pandas/Native JSON**: IMPLEMENTED for `.csv` and `.json`

## 8. Local Sync Behaviour
You can connect a local folder via the frontend or API. Clicking "Scan Now" compares the folder state against the last known state using SHA-256 hashes. It identifies `NEW`, `MODIFIED`, `UNCHANGED`, and `DELETED` files. Deleted files result in a tombstone `DELETED` event in the manifest, but their canonical historical data remains intact.

## 9. API Endpoints
- `GET /api/health`: Health check, returns `LOCAL_ONLY` mode.
- `GET /api/formats`: Returns supported formats.
- `POST /api/ingest`: Multipart upload of files and paths.
- `GET /api/sources`: List configured sync sources.
- `POST /api/sources`: Add a new sync source.
- `DELETE /api/sources/{id}`: Remove a sync source.
- `POST /api/sources/{id}/scan`: Trigger a local folder sync.

## 10. CLI Commands
Served via `uv run python -m app.main`:
- `serve`: Start the FastAPI backend and static frontend.
- `ingest --project <path>`: Ingest a local project folder directly.
- `inspect <doc_id>`: View the normalized JSON for a processed document.
- `reset`: Clear local data, sync state, or audit logs for development.

## 11. Testing
Run the test suite using `pytest`. The tests use small local fixtures only and cover:
- Hash collisions and deduplication.
- Empty files and excessively large files (Validation).
- Parser extraction validation.
- Pydantic schema validation.

## 12. Air-gapped Guarantee
This subsystem makes ZERO external network calls. There are no cloud telemetry endpoints, analytics, CDN-linked assets, or external APIs required to run the pipeline or the frontend interface.

## 13. Known Limitations
- Advanced semantic validation is not implemented.
- P&ID understanding and relationship extraction are deferred to Phase 2.
- All heavy AI parsers (Docling, Unstructured, OCR) are currently simulated.

## 14. What Phase 2 Will Consume
Phase 2 will consume the immutable `data/processed/` JSON documents. It will assume these documents are perfectly formed, validated against the Pydantic schema, and that their provenance (source, parser, timestamps) is intact and accurate.
