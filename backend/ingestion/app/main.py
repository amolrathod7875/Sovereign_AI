import argparse
import sys
import json
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.ingestion import process_project
from app.api import router as upload_router
import shutil

# Configure FastAPI application
app = FastAPI(title="Sovereign AI API")

# Include the upload API router
app.include_router(upload_router, prefix="/api")

# Mount the static frontend directory
STATIC_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

def inspect_document(doc_id: str):
    processed_file = Path(f"data/processed/{doc_id}.json")
    if not processed_file.exists():
        print(f"Error: Document {doc_id} not found in processed data.")
        sys.exit(1)
        
    with open(processed_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        print(json.dumps(data, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Local Ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the local API and Frontend server")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind")

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a project folder")
    ingest_parser.add_argument("--project", type=str, required=True, help="Path to the project folder")

    # Inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a processed document")
    inspect_parser.add_argument("doc_id", type=str, help="Document ID to inspect")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset local development state")
    reset_parser.add_argument("--local-data", action="store_true", help="Clear local ingestion state")
    reset_parser.add_argument("--sync-state", action="store_true", help="Clear sync state")
    reset_parser.add_argument("--reset-audit", action="store_true", help="Clear audit history (manifest)")

    args = parser.parse_args()

    if args.command == "serve":
        print(f"Starting server at http://{args.host}:{args.port}")
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
    elif args.command == "ingest":
        project_path = Path(args.project)
        process_project(project_path)
    elif args.command == "inspect":
        inspect_document(args.doc_id)
    elif args.command == "reset":
        if args.local_data:
            for d in ["data/raw", "data/processed", "data/incoming", "data/failed"]:
                p = Path(d)
                if p.exists():
                    shutil.rmtree(p)
                    print(f"Cleared {d}")
        if args.sync_state:
            p = Path("data/sync_state")
            if p.exists():
                shutil.rmtree(p)
                print("Cleared sync state")
        if args.reset_audit:
            p = Path("data/manifest.jsonl")
            if p.exists():
                p.unlink()
                print("Cleared audit manifest")

if __name__ == "__main__":
    main()

