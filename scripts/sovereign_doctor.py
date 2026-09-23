"""Phase 17A1 — Sovereign AI System Doctor.

Read-only diagnostic that validates environment, dependencies, assets,
and local service reachability for competition-day profiles:
  - judge
  - vision
  - coder

No downloads, no installs, no model loading, no public network calls.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Repo root: derived from this file so it works regardless of cwd
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]


_LLAMA_CPP_PROBE_SCRIPT = textwrap.dedent(
    '''
import sys
import traceback
try:
    import llama_cpp
    if hasattr(llama_cpp, "llama_cpp") and hasattr(
        llama_cpp.llama_cpp, "llama_supports_gpu_offload"
    ):
        gpu = bool(llama_cpp.llama_cpp.llama_supports_gpu_offload())
        print(f"GPU_OFFLOAD={gpu}")
    else:
        print("GPU_API_MISSING")
except Exception as e:
    print(f"ERROR={type(e).__name__}: {e}")
    traceback.print_exc(file=sys.stderr)
'''
).strip()


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------
class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    INFO = "INFO"
    FAIL = "FAIL"


class Summary(str, Enum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


@dataclass
class DoctorCheck:
    id: str
    category: str
    status: Status
    message: str
    required: bool = True
    details: Optional[str] = None
    code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class DoctorResult:
    profile: str
    checks: List[DoctorCheck] = field(default_factory=list)

    @property
    def summary(self) -> Summary:
        required_fails = [c for c in self.checks if c.required and c.status == Status.FAIL]
        if required_fails:
            return Summary.BLOCKED
        has_warn = any(c for c in self.checks if c.status == Status.WARN)
        if has_warn:
            return Summary.READY_WITH_WARNINGS
        return Summary.READY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "result": self.summary.value,
            "checks": [c.to_dict() for c in self.checks],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _add(result: DoctorResult, check: DoctorCheck) -> None:
    result.checks.append(check)


def _run(cmd: List[str], timeout: int = 15) -> subprocess.CompletedProcess:
    effective_cmd = cmd[:]
    if cmd:
        resolved = _find_command(cmd[0])
        if resolved:
            effective_cmd[0] = resolved
    if effective_cmd[0].lower().endswith((".cmd", ".bat")):
        def quote_arg(arg: str) -> str:
            if " " in arg:
                return '"' + arg + '"'
            return arg
        cmd_str = " ".join(quote_arg(a) for a in effective_cmd)
        return subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
    return subprocess.run(
        effective_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def _find_command(name: str) -> Optional[str]:
    if not name:
        return None
    p = Path(name)
    if p.is_absolute() and p.exists():
        return str(p)
    found = shutil.which(name)
    if found:
        return found
    return None


def _find_npm() -> Optional[str]:
    npm = _find_command("npm")
    if npm:
        return npm
    npm = _find_command("npm.cmd")
    if npm:
        return npm
    node = _find_command("node")
    if node:
        node_dir = Path(node).resolve().parent
        for candidate_name in ("npm.cmd", "npm.exe", "npm"):
            candidate = node_dir / candidate_name
            if candidate.exists():
                return str(candidate)
    return None


def _check_llama_cpp_subprocess() -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _LLAMA_CPP_PROBE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        if proc.returncode != 0:
            return {
                "status": "ERROR",
                "code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        if stdout.startswith("GPU_OFFLOAD="):
            val = stdout.split("=", 1)[1]
            return {
                "status": "OK",
                "gpu_ok": val == "True",
                "stdout": stdout,
            }
        if stdout.startswith("GPU_API_MISSING"):
            return {
                "status": "WARN",
                "gpu_ok": False,
                "stdout": stdout,
            }
        if stdout.startswith("ERROR="):
            err_msg = stdout.split("=", 1)[1]
            return {
                "status": "ERROR",
                "error": err_msg,
                "stdout": stdout,
                "stderr": stderr,
            }
        return {
            "status": "UNKNOWN",
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "error": str(e),
        }


def _is_os_policy_block(err_text: str) -> bool:
    t = err_text.lower()
    return "4551" in t or "application control" in t or "winerror" in t


def _http_get(url: str, timeout: float = 5.0) -> Optional[int]:
    """GET a loopback URL; return status code or None on failure."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except Exception:
        return None


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _probe_service(port: int, path: str, expect: str = "") -> Optional[str]:
    """Probe a local HTTP service. Returns 'FREE', 'EXPECTED_SERVICE', 'CONFLICT', or None."""
    if not _port_in_use(port):
        return "FREE"
    status = _http_get(f"http://127.0.0.1:{port}{path}")
    if status == 200:
        return "EXPECTED_SERVICE"
    return "CONFLICT"


# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------
def check_environment(result: DoctorResult) -> None:
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    if conda_env != "sovereign-ai":
        _add(result, DoctorCheck(
            id="env-conda",
            category="Environment",
            status=Status.FAIL,
            message=f"Wrong conda environment: {conda_env or '(not set)'}",
            required=True,
            details="Run: conda activate sovereign-ai",
        ))
        return

    _add(result, DoctorCheck(
        id="env-conda",
        category="Environment",
        status=Status.PASS,
        message=f"Conda env: {conda_env}",
    ))

    if sys.version_info.major != 3 or sys.version_info.minor != 11:
        _add(result, DoctorCheck(
            id="env-python",
            category="Environment",
            status=Status.FAIL,
            message=f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} (expected 3.11.x)",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="env-python",
            category="Environment",
            status=Status.PASS,
            message=f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ))

    exe = sys.executable
    if "anaconda3" not in exe.replace("/", "\\") or "envs" not in exe.replace("/", "\\"):
        _add(result, DoctorCheck(
            id="env-executable",
            category="Environment",
            status=Status.FAIL,
            message=f"Python executable not in conda env: {exe}",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="env-executable",
            category="Environment",
            status=Status.PASS,
            message=f"Executable resolves inside conda env: {exe}",
        ))


# ---------------------------------------------------------------------------
# Repository check
# ---------------------------------------------------------------------------
def check_repository(result: DoctorResult) -> None:
    required_paths = [
        REPO_ROOT / "backend",
        REPO_ROOT / "frontend",
        REPO_ROOT / "scripts",
        REPO_ROOT / "reports",
        REPO_ROOT / "backend" / "app" / "main.py",
        REPO_ROOT / "frontend" / "package.json",
        REPO_ROOT / "scripts" / "serve_model.py",
    ]
    all_ok = True
    missing: List[str] = []
    for p in required_paths:
        if not p.exists():
            all_ok = False
            missing.append(str(p.relative_to(REPO_ROOT)))
    if not all_ok:
        _add(result, DoctorCheck(
            id="repo-structure",
            category="Repository",
            status=Status.FAIL,
            message="Required repository paths missing",
            required=True,
            details="; ".join(missing),
        ))
    else:
        _add(result, DoctorCheck(
            id="repo-structure",
            category="Repository",
            status=Status.PASS,
            message="Repository structure intact",
        ))


# ---------------------------------------------------------------------------
# Python dependency check
# ---------------------------------------------------------------------------
def _find_spec(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _dist_version(name: str) -> Optional[str]:
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        return None


def check_python_deps(result: DoctorResult) -> None:
    deps = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("httpx", "httpx"),
        ("qdrant-client", "qdrant_client"),
        ("bm25s", "bm25s"),
        ("sentence-transformers", "sentence_transformers"),
        ("python-docx", "docx"),
        ("openpyxl", "openpyxl"),
        ("python-pptx", "pptx"),
    ]
    missing: List[str] = []
    present: List[str] = []
    for dist, mod in deps:
        if _find_spec(mod):
            ver = _dist_version(dist)
            present.append(f"{dist}{(' (' + ver + ')' if ver else '')}")
        else:
            missing.append(dist)

    if missing:
        _add(result, DoctorCheck(
            id="python-deps",
            category="Python",
            status=Status.FAIL,
            message="Missing Python dependencies",
            required=True,
            details="; ".join(missing),
        ))
    else:
        _add(result, DoctorCheck(
            id="python-deps",
            category="Python",
            status=Status.PASS,
            message=f"Core dependencies present: {', '.join(present)}",
        ))


# ---------------------------------------------------------------------------
# llama_cpp / GPU checks
# ---------------------------------------------------------------------------
def check_llama_cpp(result: DoctorResult, profile: str) -> None:
    if profile not in ("vision", "coder"):
        return

    if not _find_spec("llama_cpp"):
        _add(result, DoctorCheck(
            id="llama-cpp",
            category="Runtime",
            status=Status.FAIL,
            message="llama-cpp-python not installed",
            required=True,
        ))
        return

    ver = _dist_version("llama-cpp-python") or "unknown"
    _add(result, DoctorCheck(
        id="llama-cpp",
        category="Runtime",
        status=Status.PASS,
        message=f"llama-cpp-python {ver} installed",
        details=f"Distribution: llama-cpp-python {ver}",
    ))

    probe = _check_llama_cpp_subprocess()
    probe_text = probe.get("error") or probe.get("stdout") or probe.get("stderr") or ""

    if probe["status"] == "ERROR" and _is_os_policy_block(probe_text):
        _add(result, DoctorCheck(
            id="llama-cpp-runtime",
            category="Runtime",
            status=Status.FAIL,
            message="Windows Application Control blocked the llama.cpp native runtime. The model files are present, but the local inference runtime cannot start under the current OS policy.",
            required=True,
            code="OS_POLICY_BLOCKED_NATIVE_RUNTIME",
            details=probe_text[:500],
        ))
        return

    if probe["status"] == "ERROR":
        _add(result, DoctorCheck(
            id="llama-cpp-runtime",
            category="Runtime",
            status=Status.FAIL,
            message=f"llama-cpp-python runtime probe failed: {probe.get('error', 'unknown')}",
            required=True,
            details=probe_text[:500],
        ))
        return

    gpu_ok = probe.get("gpu_ok", False)
    if not gpu_ok and probe.get("status") == "WARN":
        _add(result, DoctorCheck(
            id="llama-gpu-offload",
            category="Runtime",
            status=Status.WARN,
            message="GPU offload API not found in installed llama-cpp-python",
            required=True,
            details=probe_text[:500],
        ))
        return

    status = Status.PASS if gpu_ok else Status.WARN
    _add(result, DoctorCheck(
        id="llama-gpu-offload",
        category="Runtime",
        status=status,
        message=f"GPU offload: {'supported' if gpu_ok else 'not detected'}",
        required=True,
        details=probe_text[:500],
    ))


# ---------------------------------------------------------------------------
# NVIDIA / GPU check
# ---------------------------------------------------------------------------
def check_nvidia(result: DoctorResult, profile: str) -> None:
    if profile not in ("vision", "coder"):
        _add(result, DoctorCheck(
            id="nvidia",
            category="GPU",
            status=Status.INFO,
            message="GPU check skipped for judge profile",
            required=False,
        ))
        return

    try:
        proc = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
        if proc.returncode != 0:
            raise RuntimeError("nvidia-smi returned non-zero")
        lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
        if not lines:
            raise RuntimeError("No GPU reported")
        parts = [p.strip() for p in lines[0].split(",")]
        name = parts[0] if len(parts) > 0 else "unknown"
        vram = parts[1] if len(parts) > 1 else "unknown"
        driver = parts[2] if len(parts) > 2 else "unknown"
        _add(result, DoctorCheck(
            id="nvidia",
            category="GPU",
            status=Status.PASS,
            message=f"GPU: {name} | VRAM: {vram} MiB | Driver: {driver}",
            required=True,
        ))
    except Exception as e:
        _add(result, DoctorCheck(
            id="nvidia",
            category="GPU",
            status=Status.FAIL,
            message="NVIDIA GPU not detected or nvidia-smi unavailable",
            required=True,
            details=str(e),
        ))


# ---------------------------------------------------------------------------
# Node / npm / frontend check
# ---------------------------------------------------------------------------
def check_frontend(result: DoctorResult) -> None:
    node_path = _find_command("node")
    npm_path = _find_npm()
    node_ok = False
    npm_ok = False
    node_ver = None
    npm_ver = None

    if node_path:
        try:
            r = _run([node_path, "--version"])
            if r.returncode == 0:
                node_ver = r.stdout.strip()
                node_ok = True
        except Exception:
            pass

    if npm_path:
        try:
            r = _run([npm_path, "--version"])
            if r.returncode == 0:
                npm_ver = r.stdout.strip()
                npm_ok = True
        except Exception:
            pass

    if not node_ok:
        _add(result, DoctorCheck(
            id="node",
            category="Frontend",
            status=Status.FAIL,
            message="Node.js not found in PATH",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="node",
            category="Frontend",
            status=Status.PASS,
            message=f"Node {node_ver}",
        ))

    if not npm_ok:
        _add(result, DoctorCheck(
            id="npm",
            category="Frontend",
            status=Status.FAIL,
            message="npm not found in PATH",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="npm",
            category="Frontend",
            status=Status.PASS,
            message=f"npm {npm_ver}",
        ))

    nm = REPO_ROOT / "frontend" / "node_modules"
    if not nm.exists() or not any(nm.iterdir()):
        _add(result, DoctorCheck(
            id="node-modules",
            category="Frontend",
            status=Status.FAIL,
            message="frontend/node_modules missing — run: npm install (in frontend/)",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="node-modules",
            category="Frontend",
            status=Status.PASS,
            message="node_modules present",
        ))


# ---------------------------------------------------------------------------
# RAG asset checks
# ---------------------------------------------------------------------------
def check_rag(result: DoctorResult) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        from rag import config as rag_config

        qdrant_path = Path(rag_config.QDRANT_PATH)
        bm25_dir = Path(rag_config.BM25_DIR)
        bm25_idx = bm25_dir / "bm25_index"
        corpus = bm25_dir / "corpus.json"
    except Exception as e:
        _add(result, DoctorCheck(
            id="rag-config",
            category="RAG",
            status=Status.FAIL,
            message="Cannot import backend/rag/config",
            required=True,
            details=str(e),
        ))
        return

    if not qdrant_path.is_dir() or not any(qdrant_path.iterdir()):
        _add(result, DoctorCheck(
            id="rag-qdrant",
            category="RAG",
            status=Status.FAIL,
            message=f"Embedded Qdrant index missing: {qdrant_path}",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="rag-qdrant",
            category="RAG",
            status=Status.PASS,
            message=f"Embedded Qdrant index present: {qdrant_path}",
        ))

    if not bm25_idx.exists() or not corpus.exists():
        _add(result, DoctorCheck(
            id="rag-bm25",
            category="RAG",
            status=Status.FAIL,
            message=f"BM25 index or corpus missing at {bm25_dir}",
            required=True,
        ))
    else:
        chunk_count = None
        try:
            with open(corpus, encoding="utf-8") as f:
                data = json.load(f)
                chunk_count = len(data.get("order", []))
        except Exception:
            pass
        msg = f"BM25 index present at {bm25_dir}"
        if chunk_count is not None:
            msg += f" ({chunk_count} chunks)"
        _add(result, DoctorCheck(
            id="rag-bm25",
            category="RAG",
            status=Status.PASS,
            message=msg,
        ))


# ---------------------------------------------------------------------------
# Local embedding check
# ---------------------------------------------------------------------------
def check_embeddings(result: DoctorResult) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        from rag import config as rag_config

        emb_path = Path(rag_config.EMBEDDING_MODEL)
    except Exception as e:
        _add(result, DoctorCheck(
            id="embeddings",
            category="Embeddings",
            status=Status.FAIL,
            message="Cannot resolve embedding model path",
            required=True,
            details=str(e),
        ))
        return

    if not emb_path.exists() or not emb_path.is_dir():
        _add(result, DoctorCheck(
            id="embeddings",
            category="Embeddings",
            status=Status.FAIL,
            message=f"Embedding model directory missing: {emb_path}",
            required=True,
        ))
    elif not any(emb_path.iterdir()):
        _add(result, DoctorCheck(
            id="embeddings",
            category="Embeddings",
            status=Status.FAIL,
            message=f"Embedding model directory empty: {emb_path}",
            required=True,
        ))
    else:
        _add(result, DoctorCheck(
            id="embeddings",
            category="Embeddings",
            status=Status.PASS,
            message=f"Local embedding model present: {emb_path}",
        ))


# ---------------------------------------------------------------------------
# Competition evidence checks
# ---------------------------------------------------------------------------
def check_evidence(result: DoctorResult) -> None:
    flagship = REPO_ROOT / "reports" / "flagship_workflow_latest.json"
    scorecard = REPO_ROOT / "reports" / "competition_scorecard.json"

    for path, cid, label in [(flagship, "flagship", "Flagship workflow"), (scorecard, "scorecard", "Evaluation scorecard")]:
        if not path.exists():
            _add(result, DoctorCheck(
                id=cid,
                category="Evidence",
                status=Status.FAIL,
                message=f"{label} report missing: {path.name}",
                required=True,
            ))
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            details_parts = []
            if cid == "flagship":
                ts = data.get("timestamp") or data.get("run_timestamp") or data.get("created_at")
                rid = data.get("run_id") or data.get("id")
                if ts:
                    details_parts.append(f"timestamp: {ts}")
                if rid:
                    details_parts.append(f"run_id: {rid}")
            else:
                gen = data.get("generated_at") or data.get("timestamp")
                commit = data.get("repository_commit") or data.get("commit")
                if gen:
                    details_parts.append(f"generated_at: {gen}")
                if commit:
                    details_parts.append(f"repository_commit: {commit}")
            _add(result, DoctorCheck(
                id=cid,
                category="Evidence",
                status=Status.PASS,
                message=f"{label} readable: {path.name}",
                details="; ".join(details_parts) if details_parts else None,
            ))
        except json.JSONDecodeError as e:
            _add(result, DoctorCheck(
                id=cid,
                category="Evidence",
                status=Status.FAIL,
                message=f"{label} malformed JSON: {path.name}",
                required=True,
                details=str(e),
            ))
        except Exception as e:
            _add(result, DoctorCheck(
                id=cid,
                category="Evidence",
                status=Status.FAIL,
                message=f"{label} unreadable: {path.name}",
                required=True,
                details=str(e),
            ))


# ---------------------------------------------------------------------------
# Judge API source check
# ---------------------------------------------------------------------------
def check_judge_sources(result: DoctorResult) -> None:
    paths = [
        REPO_ROOT / "backend" / "judge" / "service.py",
        REPO_ROOT / "backend" / "app" / "api" / "judge.py",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in paths if not p.exists()]
    if missing:
        _add(result, DoctorCheck(
            id="judge-sources",
            category="Packaging",
            status=Status.FAIL,
            message="Phase 16 Judge API source files missing",
            required=True,
            details="; ".join(missing),
        ))
    else:
        _add(result, DoctorCheck(
            id="judge-sources",
            category="Packaging",
            status=Status.PASS,
            message="Phase 16 Judge API sources present",
        ))


# ---------------------------------------------------------------------------
# Governance storage check
# ---------------------------------------------------------------------------
def check_governance(result: DoctorResult) -> None:
    gov_dir = REPO_ROOT / "data" / "governance"
    db_path = gov_dir / "approvals.sqlite3"
    if db_path.exists():
        _add(result, DoctorCheck(
            id="governance",
            category="Storage",
            status=Status.INFO,
            message="Governance DB exists",
            required=False,
            details=str(db_path),
        ))
    else:
        if gov_dir.exists() or True:
            _add(result, DoctorCheck(
                id="governance",
                category="Storage",
                status=Status.INFO,
                message="Governance DB not yet created — will be created on first use",
                required=False,
                details=str(db_path),
            ))
        else:
            _add(result, DoctorCheck(
                id="governance",
                category="Storage",
                status=Status.WARN,
                message="Governance parent directory missing",
                required=False,
                details=str(gov_dir),
            ))


# ---------------------------------------------------------------------------
# Model file checks
# ---------------------------------------------------------------------------
def check_model_files(result: DoctorResult, profile: str) -> None:
    models_dir = REPO_ROOT / "models"

    if profile in ("vision", "coder", "judge"):
        general_dir = models_dir / "qwen-general"
        if not general_dir.exists() or not any(general_dir.glob("*.gguf")):
            _add(result, DoctorCheck(
                id="general-weights",
                category="Models",
                status=Status.INFO,
                message="General weights absent — expected unavailable",
                required=False,
                details=str(general_dir),
            ))

    if profile == "vision":
        vision_gguf = models_dir / "qwen-vision" / "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
        mmproj = models_dir / "qwen-vision" / "mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"
        if not vision_gguf.exists():
            _add(result, DoctorCheck(
                id="vision-gguf",
                category="Models",
                status=Status.FAIL,
                message="Vision GGUF missing",
                required=True,
                details=str(vision_gguf),
            ))
        else:
            _add(result, DoctorCheck(
                id="vision-gguf",
                category="Models",
                status=Status.PASS,
                message=f"Vision GGUF present: {vision_gguf.name}",
            ))
        if not mmproj.exists():
            _add(result, DoctorCheck(
                id="vision-mmproj",
                category="Models",
                status=Status.FAIL,
                message="Vision mmproj missing",
                required=True,
                details=str(mmproj),
            ))
        else:
            _add(result, DoctorCheck(
                id="vision-mmproj",
                category="Models",
                status=Status.PASS,
                message=f"Vision mmproj present: {mmproj.name}",
            ))

    if profile == "coder":
        coder_gguf = models_dir / "qwen-coder" / "qwen2.5-coder-3b-instruct-q4_k_m.gguf"
        if not coder_gguf.exists():
            _add(result, DoctorCheck(
                id="coder-gguf",
                category="Models",
                status=Status.FAIL,
                message="Coder GGUF missing",
                required=True,
                details=str(coder_gguf),
            ))
        else:
            _add(result, DoctorCheck(
                id="coder-gguf",
                category="Models",
                status=Status.PASS,
                message=f"Coder GGUF present: {coder_gguf.name}",
            ))

    if profile == "judge":
        _add(result, DoctorCheck(
            id="coder-gguf",
            category="Models",
            status=Status.INFO,
            message="Coder GGUF not required for judge profile",
            required=False,
        ))
        _add(result, DoctorCheck(
            id="vision-gguf",
            category="Models",
            status=Status.INFO,
            message="Vision GGUF not required for judge profile",
            required=False,
        ))
        _add(result, DoctorCheck(
            id="vision-mmproj",
            category="Models",
            status=Status.INFO,
            message="Vision mmproj not required for judge profile",
            required=False,
        ))


# ---------------------------------------------------------------------------
# Port checks
# ---------------------------------------------------------------------------
def check_ports(result: DoctorResult, profile: str) -> None:
    ports = {
        3000: ("/", "Frontend"),
        8000: ("/api/system/health", "Backend"),
        8001: ("/v1/models", "General"),
        8002: ("/v1/models", "Coder"),
        8003: ("/v1/models", "Vision"),
    }
    for port, (path, label) in ports.items():
        state = _probe_service(port, path)
        if state == "FREE":
            msg = f"Port {port} free"
            if port == 8001:
                msg = f"Port {port} free — general runtime expected unavailable"
            _add(result, DoctorCheck(
                id=f"port-{port}",
                category="Ports",
                status=Status.INFO if port == 8001 else Status.PASS,
                message=msg,
                required=(port in (3000, 8000)),
            ))
        elif state == "EXPECTED_SERVICE":
            _add(result, DoctorCheck(
                id=f"port-{port}",
                category="Ports",
                status=Status.PASS,
                message=f"Port {port}: {label} already running",
            ))
        else:
            _add(result, DoctorCheck(
                id=f"port-{port}",
                category="Ports",
                status=Status.FAIL,
                message=f"Port {port} occupied by unrecognized process",
                required=(port in (3000, 8000)),
                details=f"Expected {label} on port {port}",
            ))


# ---------------------------------------------------------------------------
# Optional services
# ---------------------------------------------------------------------------
def check_optional(result: DoctorResult) -> None:
    optional = [
        ("Docker", ["docker", "--version"]),
        ("PostgreSQL", None),  # custom check
        ("Qdrant HTTP", None),  # custom check
        ("Piston", None),  # custom check
    ]
    for name, cmd in optional:
        if name == "Docker":
            try:
                r = _run(cmd)
                if r.returncode == 0:
                    _add(result, DoctorCheck(
                        id=f"opt-{name.lower().replace(' ', '-')}",
                        category="Optional",
                        status=Status.INFO,
                        message=f"{name} available: {r.stdout.strip()}",
                        required=False,
                    ))
                else:
                    _add(result, DoctorCheck(
                        id=f"opt-{name.lower().replace(' ', '-')}",
                        category="Optional",
                        status=Status.INFO,
                        message=f"{name} not available",
                        required=False,
                    ))
            except Exception:
                _add(result, DoctorCheck(
                    id=f"opt-{name.lower().replace(' ', '-')}",
                    category="Optional",
                    status=Status.INFO,
                    message=f"{name} not available",
                    required=False,
                ))
        elif name == "PostgreSQL":
            in_use = _port_in_use(5432)
            _add(result, DoctorCheck(
                id="opt-postgresql",
                category="Optional",
                status=Status.INFO,
                message=f"PostgreSQL port 5432: {'in use' if in_use else 'free'}",
                required=False,
            ))
        elif name == "Qdrant HTTP":
            in_use = _port_in_use(6333)
            _add(result, DoctorCheck(
                id="opt-qdrant-http",
                category="Optional",
                status=Status.INFO,
                message=f"Qdrant HTTP port 6333: {'in use' if in_use else 'free'}",
                required=False,
            ))
        elif name == "Piston":
            in_use = _port_in_use(2000)
            _add(result, DoctorCheck(
                id="opt-piston",
                category="Optional",
                status=Status.INFO,
                message=f"Piston port 2000: {'in use' if in_use else 'free'}",
                required=False,
            ))


# ---------------------------------------------------------------------------
# Backend importability
# ---------------------------------------------------------------------------
def check_backend_import(result: DoctorResult) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        import io
        import contextlib

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import app.main  # noqa: F401

        _add(result, DoctorCheck(
            id="backend-import",
            category="Backend",
            status=Status.PASS,
            message="backend.app.main importable",
        ))
    except Exception as e:
        _add(result, DoctorCheck(
            id="backend-import",
            category="Backend",
            status=Status.FAIL,
            message="Cannot import backend.app.main",
            required=True,
            details=str(e),
        ))


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------
def _build_doctor_result(profile: str) -> DoctorResult:
    profile = profile.lower()
    if profile not in ("judge", "vision", "coder"):
        raise ValueError(f"Unknown profile: {profile}")
    result = DoctorResult(profile=profile)
    check_environment(result)
    check_repository(result)
    check_python_deps(result)
    check_backend_import(result)
    check_frontend(result)
    check_rag(result)
    check_embeddings(result)
    check_evidence(result)
    check_judge_sources(result)
    check_governance(result)
    check_ports(result, profile)
    check_optional(result)
    check_model_files(result, profile)
    check_llama_cpp(result, profile)
    check_nvidia(result, profile)
    return result


def run_doctor(profile: str, json_output: bool = False) -> int:
    result = _build_doctor_result(profile)
    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.summary in (Summary.READY, Summary.READY_WITH_WARNINGS) else 1

    for c in result.checks:
        prefix = f"[{c.status.value}]"
        print(f"{prefix:<8} {c.category:<14} {c.message}")
        if c.details and c.status == Status.FAIL:
            print(f"         Details: {c.details}")

    print()
    print(f"Result: {result.summary.value}")
    return 0 if result.summary in (Summary.READY, Summary.READY_WITH_WARNINGS) else 1


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Sovereign AI System Doctor — competition-day readiness checks",
    )
    parser.add_argument(
        "command",
        choices=["doctor", "start", "status", "stop"],
        help="Launcher command",
    )
    parser.add_argument(
        "--profile",
        choices=["judge", "vision", "coder"],
        help="Competition profile (required for doctor/start)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text (doctor only)",
    )
    args = parser.parse_args()

    if args.command == "doctor":
        if not args.profile:
            print("--profile is required for doctor", file=sys.stderr)
            return 2
        return run_doctor(args.profile, json_output=args.json)

    print("Launcher commands are handled by scripts/sovereign.py", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
