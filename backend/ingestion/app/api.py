from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import shutil
import datetime
from pathlib import Path

from app.ingestion import process_project
from app.sync import get_sources, add_source, remove_source, scan_source

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "mode": "LOCAL_ONLY"
    }

@router.get("/formats")
async def get_formats():
    return {
        "supported": [
            ".pdf",
            ".docx",
            ".pptx",
            ".xlsx",
            ".csv",
            ".txt",
            ".json",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff"
        ]
    }

@router.post("/ingest")
async def ingest_project(
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(...)
):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_id = f"UPLOAD_{timestamp}"

    # Determine a project name
    if paths and len(paths) > 0 and "/" in paths[0]:
        project_name = paths[0].split("/")[0]
    elif paths and len(paths) > 0 and "\\" in paths[0]:
        project_name = paths[0].split("\\")[0]
    else:
        project_name = upload_id

    # Stage inside data/incoming/<upload_id>
    staging_dir = Path("data/incoming") / upload_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Save files to staging area, preserving directory structure
    for upload_file, relative_path in zip(files, paths):
        if not relative_path:
            relative_path = upload_file.filename
            
        file_dest = staging_dir / relative_path
        
        # Ensure parent directories exist
        file_dest.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_dest, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

    # Invoke the existing ingestion pipeline
    stats = process_project(staging_dir)

    import hashlib
    project_hash = hashlib.sha256(str(staging_dir.absolute()).encode()).hexdigest()
    project_id = f"PROJECT-{project_hash[:8].upper()}"

    return {
        "project_id": project_id,
        "status": "completed",
        "discovered": stats["discovered"],
        "processed": stats["processed"],
        "duplicates": stats["duplicates"],
        "failed": stats["failed"],
        "network_calls": 0,
        "files": stats["files"]
    }

class SourceCreateRequest(BaseModel):
    name: str
    path: str

@router.get("/sources")
async def get_all_sources():
    return get_sources()

@router.post("/sources")
async def create_source(req: SourceCreateRequest):
    return add_source(req.name, req.path)

@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    success = remove_source(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "success"}

@router.post("/sources/{source_id}/scan")
async def scan_specific_source(source_id: str):
    try:
        stats = scan_source(source_id)
        return {
            "status": "completed",
            "source_id": source_id,
            "stats": stats
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
