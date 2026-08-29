import os
import sys
import json
import hashlib
import shutil
import datetime
import traceback
from pathlib import Path
from pydantic import ValidationError

from app.models import (
    Document, SourceInfo, FileInfo, Metadata, 
    DocumentContent, IngestionInfo
)
from app.parsers import detect_file_info, process_file
from app.config import DATA_DIR, MAX_FILE_SIZE_BYTES, setup_logger

logger = setup_logger("ingestion")

RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FAILED_DIR = DATA_DIR / "failed"
MANIFEST_FILE = DATA_DIR / "manifest.jsonl"

class ExtractionEmptyError(Exception):
    pass

def setup_directories():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Add gitkeep files
    for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR, FAILED_DIR]:
        (d / ".gitkeep").touch(exist_ok=True)

def get_sha256(filepath: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_processed_hashes() -> set:
    if not MANIFEST_FILE.exists():
        return set()
    
    hashes = set()
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    if entry.get("status") == "processed":
                        file_hash = entry.get("sha256")
                        if file_hash:
                            doc_id = generate_document_id(file_hash)
                            if (PROCESSED_DIR / f"{doc_id}.json").exists() and (RAW_DIR / doc_id).exists():
                                hashes.add(file_hash)
                except json.JSONDecodeError:
                    pass
    return hashes

def append_to_manifest(entry: dict):
    with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def generate_document_id(file_hash: str) -> str:
    return f"DOC-{file_hash[:12].upper()}"

def generate_project_id(project_path: Path) -> str:
    project_hash = hashlib.sha256(str(project_path.absolute()).encode()).hexdigest()
    return f"PROJECT-{project_hash[:8].upper()}"

def process_project(project_path: Path):
    setup_directories()
    
    if not project_path.exists() or not project_path.is_dir():
        print(f"Error: Project directory {project_path} does not exist.")
        sys.exit(1)
    
    project_id = generate_project_id(project_path)
    processed_hashes = get_processed_hashes()
    
    stats = {
        "discovered": 0,
        "processed": 0,
        "duplicates": 0,
        "failed": 0,
        "files": []
    }
    
    logger.info(f"Starting ingestion for project: {project_path.name}")
    
    print("=" * 40)
    print("       SOVEREIGN AI INGESTION")
    print("=" * 40)
    print(f"\nProject: {project_path.name}")
    print()

    for root, _, files in os.walk(project_path):
        for file in files:
            filepath = Path(root) / file
            
            # Skip hidden files
            if file.startswith('.'):
                continue
                
            stats["discovered"] += 1
            
            try:
                file_size = filepath.stat().st_size
                
                if file_size == 0:
                    raise ValueError("EMPTY_FILE: File is 0 bytes")
                
                if file_size > MAX_FILE_SIZE_BYTES:
                    raise ValueError(f"FILE_TOO_LARGE: File size {file_size} exceeds maximum {MAX_FILE_SIZE_BYTES}")
                
                file_hash = get_sha256(filepath)
                
                if file_hash in processed_hashes:
                    document_id = generate_document_id(file_hash)
                    logger.info(f"Duplicate detected: {file} ({file_hash})")
                    stats["duplicates"] += 1
                    stats["files"].append({
                        "filename": file,
                        "relative_path": str(filepath.relative_to(project_path.parent)),
                        "status": "duplicate",
                        "document_id": document_id,
                        "parser": "unknown",
                        "error": "Already stored"
                    })
                    
                    # Record duplicate in manifest
                    manifest_entry = {
                        "event_type": "DUPLICATE",
                        "document_id": document_id,
                        "existing_document_id": document_id,
                        "upload_id": project_path.name,
                        "project_id": project_id,
                        "filename": file,
                        "status": "duplicate",
                        "sha256": file_hash,
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
                    }
                    append_to_manifest(manifest_entry)
                    continue
                
                document_id = generate_document_id(file_hash)
                logger.info(f"Processing new file: {file} -> {document_id}")
                
                # Copy to raw
                raw_file_dir = RAW_DIR / document_id
                raw_file_dir.mkdir(exist_ok=True)
                raw_file_path = raw_file_dir / file
                shutil.copy2(filepath, raw_file_path)
                
                # Detect and Parse
                mime_type, parser_name = detect_file_info(filepath)
                
                content_dict = process_file(filepath, parser_name)
                
                # Validation of Extraction Quality
                has_pages = bool(content_dict.get("pages"))
                has_records = bool(content_dict.get("records"))
                has_text = bool(content_dict.get("raw_text"))
                if not (has_pages or has_records or has_text):
                    raise ExtractionEmptyError(f"EXTRACTION_EMPTY: Parser {parser_name} returned no content for {file}")
                
                extraction_status = "SUCCESS"
                
                # Build Document
                relative_path = str(filepath.relative_to(project_path.parent))
                
                # Retrieve timestamps
                stat = filepath.stat()
                created_date = datetime.datetime.fromtimestamp(stat.st_ctime, datetime.UTC).isoformat() if hasattr(stat, 'st_ctime') else None
                modified_date = datetime.datetime.fromtimestamp(stat.st_mtime, datetime.UTC).isoformat() if hasattr(stat, 'st_mtime') else None
                
                doc = Document(
                    document_id=document_id,
                    project_id=project_id,
                    source=SourceInfo(
                        filename=file,
                        relative_path=relative_path,
                        type="local_project"
                    ),
                    file=FileInfo(
                        mime_type=mime_type,
                        size_bytes=file_size,
                        sha256=file_hash
                    ),
                    metadata=Metadata(
                        title=filepath.stem,
                        created_date=created_date,
                        modified_date=modified_date
                    ),
                    content=DocumentContent(**content_dict),
                    ingestion=IngestionInfo(
                        parser=parser_name,
                        processed_at=datetime.datetime.now(datetime.UTC).isoformat(),
                        status="processed",
                        extraction_status=extraction_status
                    )
                )
                
                # Save Processed JSON
                processed_filepath = PROCESSED_DIR / f"{document_id}.json"
                with open(processed_filepath, "w", encoding="utf-8") as f:
                    f.write(doc.model_dump_json(indent=2))
                
                # Update manifest
                manifest_entry = {
                    "event_type": "INGESTED",
                    "document_id": document_id,
                    "project_id": project_id,
                    "filename": file,
                    "relative_path": relative_path,
                    "status": "processed",
                    "sha256": file_hash,
                    "parser": parser_name,
                    "timestamp": doc.ingestion.processed_at
                }
                append_to_manifest(manifest_entry)
                processed_hashes.add(file_hash)
                
                stats["processed"] += 1
                stats["files"].append({
                    "filename": file,
                    "relative_path": relative_path,
                    "status": "processed",
                    "document_id": document_id,
                    "parser": parser_name
                })
                
                logger.info(f"Successfully processed {file} -> {document_id}")
                
            except Exception as e:
                # Handle Failure
                logger.error(f"Failed to process {file}: {e}")
                stats["failed"] += 1
                stats["files"].append({
                    "filename": file,
                    "relative_path": str(filepath.relative_to(project_path.parent)) if 'filepath' in locals() else file,
                    "status": "failed",
                    "error": str(e)
                })
                
                safe_hash = file_hash[:12].upper() if 'file_hash' in locals() and file_hash else "UNKNOWN_HASH"
                failed_file_dir = FAILED_DIR / safe_hash
                failed_file_dir.mkdir(exist_ok=True)
                
                try:
                    shutil.copy2(filepath, failed_file_dir / file)
                except:
                    pass # Best effort copy
                
                error_info = {
                    "filename": file,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
                }
                with open(failed_file_dir / "error.json", "w", encoding="utf-8") as f:
                    json.dump(error_info, f, indent=2)
                    
                append_to_manifest({
                    "event_type": "FAILED",
                    "filename": file,
                    "status": "failed",
                    "sha256": get_sha256(filepath) if filepath.exists() and filepath.stat().st_size > 0 else "unknown",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
                })

    # Print Summary
    print(f"Discovered: {stats['discovered']}")
    print(f"Processed: {stats['processed']}")
    print(f"Duplicates: {stats['duplicates']}")
    print(f"Failed: {stats['failed']}")
    print()
    
    for file_info in stats["files"]:
        status = file_info.get("status")
        status_char = "[OK]" if status in ("processed", "duplicate") else "[FAIL]"
        print(f"{status_char} {file_info.get('filename')}")
        
    print("\nOriginals preserved: YES")
    print("Processing: LOCAL ONLY")
    print("\n" + "=" * 40)
    print("         INGESTION COMPLETE")
    print("=" * 40)

    return stats
