import json
import uuid
import datetime
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple

from app.ingestion import get_sha256, process_project, append_to_manifest
from app.config import setup_logger

logger = setup_logger("sync")

SYNC_STATE_DIR = Path("data/sync_state")

def _init_sync_state():
    SYNC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    sources_file = SYNC_STATE_DIR / "sources.json"
    if not sources_file.exists():
        with open(sources_file, "w", encoding="utf-8") as f:
            json.dump([], f)

def get_sources() -> list:
    _init_sync_state()
    sources_file = SYNC_STATE_DIR / "sources.json"
    with open(sources_file, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_sources(sources: list):
    _init_sync_state()
    sources_file = SYNC_STATE_DIR / "sources.json"
    with open(sources_file, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2)

def add_source(name: str, path: str) -> dict:
    sources = get_sources()
    source_id = f"SRC-{uuid.uuid4().hex[:8].upper()}"
    source = {
        "id": source_id,
        "name": name,
        "path": path,
        "status": "LOCAL",
        "last_scan": None,
        "files_count": 0
    }
    sources.append(source)
    _save_sources(sources)
    return source

def remove_source(source_id: str) -> bool:
    sources = get_sources()
    new_sources = [s for s in sources if s["id"] != source_id]
    if len(new_sources) == len(sources):
        return False
    _save_sources(new_sources)
    
    state_file = SYNC_STATE_DIR / f"{source_id}_files.json"
    if state_file.exists():
        state_file.unlink()
    return True

def get_source_state(source_id: str) -> dict:
    state_file = SYNC_STATE_DIR / f"{source_id}_files.json"
    if not state_file.exists():
        return {}
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_source_state(source_id: str, state: dict):
    state_file = SYNC_STATE_DIR / f"{source_id}_files.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def scan_source(source_id: str) -> dict:
    sources = get_sources()
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        raise ValueError(f"Source {source_id} not found")
        
    source_path = Path(source["path"])
    if not source_path.exists() or not source_path.is_dir():
        raise ValueError(f"Directory {source_path} does not exist")
        
    old_state = get_source_state(source_id)
    new_state = {}
    
    # Track stats
    stats = {
        "new": 0,
        "modified": 0,
        "unchanged": 0,
        "deleted": 0,
        "failed": 0
    }
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_id = f"SYNC_{timestamp}"
    staging_dir = Path("data/incoming") / upload_id
    
    staged_files_count = 0
    
    for filepath in source_path.rglob('*'):
        if not filepath.is_file():
            continue
            
        if filepath.name.startswith('.'):
            continue
            
        rel_path_str = str(filepath.relative_to(source_path))
        rel_path_str = rel_path_str.replace('\\', '/')
        
        try:
            current_hash = get_sha256(filepath)
        except Exception:
            stats["failed"] += 1
            continue
            
        # Determine status
        is_staged = False
        if rel_path_str not in old_state:
            stats["new"] += 1
            is_staged = True
        else:
            if old_state[rel_path_str]["sha256"] == current_hash:
                stats["unchanged"] += 1
                new_state[rel_path_str] = old_state[rel_path_str]
            else:
                stats["modified"] += 1
                is_staged = True
                
        if is_staged:
            dest = staging_dir / rel_path_str
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, dest)
            staged_files_count += 1
            new_state[rel_path_str] = {
                "sha256": current_hash,
                "document_id": None # Will be filled after process_project
            }
            
    # Find deleted files
    for rel_path_str, data in old_state.items():
        if rel_path_str not in new_state:
            stats["deleted"] += 1
            logger.info(f"File deleted: {rel_path_str}")
            # Record deletion tombstone in manifest
            manifest_entry = {
                "event_type": "DELETED",
                "status": "deleted",
                "filename": rel_path_str,
                "document_id": data.get("document_id"),
                "source_id": source_id,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
            }
            append_to_manifest(manifest_entry)
            
    # If we staged files, run ingestion
    if staged_files_count > 0:
        logger.info(f"Processing {staged_files_count} staged files for source {source_id}")
        process_stats = process_project(staging_dir)
        
        # Map the generated document IDs back to the new state
        for file_res in process_stats.get("files", []):
            res_rel_path = file_res.get("relative_path", "")
            # Path parsing to align formatting back to standard slashes
            parts = Path(res_rel_path).parts
            if len(parts) > 1:
                clean_rel_path = "/".join(parts[1:])
                if clean_rel_path in new_state:
                    # Check if this was a modification and log the MODIFIED event
                    if clean_rel_path in old_state and old_state[clean_rel_path]["sha256"] != new_state[clean_rel_path]["sha256"]:
                        manifest_entry = {
                            "event_type": "MODIFIED",
                            "status": "modified",
                            "filename": clean_rel_path,
                            "new_document_id": file_res.get("document_id"),
                            "old_document_id": old_state[clean_rel_path].get("document_id"),
                            "source_id": source_id,
                            "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
                        }
                        append_to_manifest(manifest_entry)
                        logger.info(f"File modified: {clean_rel_path}")
                        
                    new_state[clean_rel_path]["document_id"] = file_res.get("document_id")

    _save_source_state(source_id, new_state)
    
    source["last_scan"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    source["files_count"] = len(new_state)
    _save_sources(sources)
    
    return stats
