# Sovereign AI Workbench - MRPL

## Phase 1.5 - Local Upload Frontend

This project includes a local, air-gapped web interface to easily upload documents (files or whole folders) into the Sovereign AI ingestion core.

### Architecture Overview

The system is separated into a thin frontend API layer and a heavy backend ingestion core. This separation allows future developers to replace or improve the frontend UI completely without changing how data is parsed, hashed, normalized, and validated.

```text
Frontend (Vanilla HTML/JS)
   │
   │ POST /api/ingest
   ▼
FastAPI API (app.api.upload)
   │
   ▼
app.ingestion.process_project()
   │
   ├── parsers.py
   ├── models.py
   ├── hashing
   └── storage
   │
   ▼
data/
```

### Running the Application

Both the backend API and the frontend are served via a single command:

```bash
uv run python -m app.main serve
```

*By default, the server runs on `http://127.0.0.1:8000`.*
You can then open your browser and navigate to `http://localhost:8000`.

*Note: The original CLI commands (`ingest` and `inspect`) are fully preserved and still functional.*

### API Endpoints

- **`GET /api/health`**
  Returns `{ "status": "ok", "mode": "LOCAL_ONLY" }`.
- **`GET /api/formats`**
  Returns a JSON array of supported file extensions (e.g. `[".pdf", ".docx", ...]`). The frontend fetches this dynamically.
- **`POST /api/ingest`**
  Accepts a `multipart/form-data` payload containing:
  - `files`: Multiple file objects.
  - `paths`: Parallel array of relative paths for each file (this preserves the folder hierarchy).
  - `project_name` (optional): The name of the project.

#### Folder Upload Behavior

When a folder is selected or dropped onto the frontend dropzone, the browser extracts the relative paths of all nested files. The frontend sends these relative paths (e.g. `Engineering/P204_PID.pdf`) to the backend via the `paths` form field. The backend stages the files into the `data/incoming/` directory, exactly recreating the original directory structure before invoking the ingestion core.

### File Storage Locations

- **Staging Area**: Files uploaded via the API are temporarily staged in `data/incoming/{project_name}/`.
- **Raw Storage**: After processing starts, copies are placed in `data/raw/{document_id}/`.
- **Processed Storage**: The normalized Pydantic JSON schemas are stored in `data/processed/{document_id}.json`.
- **Failed Storage**: Corrupted or unparseable files are stored in `data/failed/`.
- **Manifest**: Every processed file is logged in `data/manifest.jsonl`.

### Response Schema

The `/api/ingest` endpoint returns a summary of the ingestion process:

```json
{
  "project_id": "PROJECT-XYZ123",
  "status": "completed",
  "discovered": 5,
  "processed": 4,
  "duplicates": 0,
  "failed": 1,
  "network_calls": 0,
  "files": [
    {
      "filename": "P204_PID.pdf",
      "relative_path": "Engineering/P204_PID.pdf",
      "status": "processed",
      "document_id": "DOC-ABCDEF123456",
      "parser": "docling_simulated"
    }
  ]
}
```

### Future Frontend Replacement

Since the frontend is just static HTML/JS communicating with a FastAPI endpoint, a future React, Vue, or Svelte developer can simply:
1. Ignore `app/static/`.
2. Build their own SPA.
3. Post `multipart/form-data` to `http://localhost:8000/api/ingest` adhering to the required payload schema.
The backend ingestion core will remain completely untouched.
