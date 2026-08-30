"""Artifact retrieval (read-only).

Phase 6 gap fix: the platform already GENERATES artifacts — the authoritative agent
writes DOCX approval notes via ``agent/tools/create_docx.py`` into
``agent.config.OUTPUT_DIR`` and the coding agent writes its deliverables via
``agent/coder/artifact.py``. There was, however, no way for a client to LIST or
DOWNLOAD them, so the frontend could not expose the artifact workflow.

This router is retrieval-only:
  GET /api/artifacts                     -> list artifacts already on disk
  GET /api/artifacts/{artifact_id}       -> metadata for one artifact
  GET /api/artifacts/{artifact_id}/download -> stream the file

It creates NO artifact generation path of its own.

Security
--------
* Artifact ids are ``sha1`` digests of the resolved absolute path, so a client can
  never express a path (no traversal surface at all).
* Only files under the configured artifact roots and with an allow-listed
  extension are ever enumerated or served.
"""
import hashlib
import logging
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import ArtifactInfo

logger = logging.getLogger(__name__)
router = APIRouter()

# Extension -> artifact kind shown in the UI. Only these are served.
_KINDS: Dict[str, str] = {
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".pptx": "PPTX",
    ".pdf": "PDF",
    ".py": "CODE",
    ".md": "MARKDOWN",
    ".json": "JSON",
    ".csv": "CSV",
    ".txt": "TEXT",
}

_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def _roots() -> List[Path]:
    """Directories the authoritative components write artifacts into."""
    out: List[Path] = []
    for raw in (
        settings.AGENT_OUTPUT_DIR,   # data/outputs   (agent DOCX + coder_demo/)
        settings.ARTIFACT_DIR,       # data/artifacts (container deploy)
    ):
        try:
            p = Path(raw).resolve()
        except Exception:
            continue
        if p.is_dir() and p not in out:
            out.append(p)
    # Coder workspaces (generated solution.py / test_solution.py) — read-only.
    try:
        from agent.coder.config import CODER_DIR

        p = Path(CODER_DIR).resolve()
        if p.is_dir() and p not in out:
            out.append(p)
    except Exception:
        pass
    return out


def artifact_id_for(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def _run_id_for(path: Path, root: Path) -> Optional[str]:
    """Best-effort run id: parent directory name, else parsed from the filename."""
    try:
        rel = path.resolve().relative_to(root)
    except Exception:
        return None
    if len(rel.parts) > 1:
        return rel.parts[-2]
    stem = path.stem
    for marker in ("run_", "coder_"):
        if marker in stem:
            return marker + stem.split(marker, 1)[1]
    return None


def _describe(path: Path, root: Path) -> Optional[ArtifactInfo]:
    ext = path.suffix.lower()
    kind = _KINDS.get(ext)
    if kind is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return ArtifactInfo(
        artifact_id=artifact_id_for(path),
        filename=path.name,
        kind=kind,
        size=st.st_size,
        mime_type=mime,
        modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        run_id=_run_id_for(path, root),
    )


def _scan() -> List[tuple]:
    """Return [(ArtifactInfo, Path)] for every servable artifact, newest first."""
    found: List[tuple] = []
    for root in _roots():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
            for name in filenames:
                p = Path(dirpath) / name
                info = _describe(p, root)
                if info is not None:
                    found.append((info, p))
    found.sort(key=lambda t: t[0].modified_at, reverse=True)
    return found


def _find(artifact_id: str) -> Optional[tuple]:
    for info, path in _scan():
        if info.artifact_id == artifact_id:
            return info, path
    return None


@router.get("")
async def list_artifacts(
    limit: int = Query(100, ge=1, le=1000),
    run_id: Optional[str] = None,
    kind: Optional[str] = None,
) -> List[ArtifactInfo]:
    items = [info for info, _ in _scan()]
    if run_id:
        items = [i for i in items if i.run_id == run_id]
    if kind:
        items = [i for i in items if i.kind.upper() == kind.upper()]
    return items[:limit]


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str) -> ArtifactInfo:
    hit = _find(artifact_id)
    if hit is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return hit[0]


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    hit = _find(artifact_id)
    if hit is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    info, path = hit
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Artifact file no longer on disk")
    return FileResponse(
        path=str(path),
        media_type=info.mime_type,
        filename=info.filename,
        headers={"Cache-Control": "no-store"},
    )
