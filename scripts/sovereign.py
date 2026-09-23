"""Phase 17A1 — Sovereign AI Competition Launcher.

Provides commands:
  doctor  -- profile-aware readiness check
  start   -- launch a competition profile
  status  -- show launcher state and service probes
  stop    -- stop launcher-owned processes

Profiles:
  judge  — backend + frontend (no model server)
  vision — vision model + backend + frontend
  coder  — coder model + backend + frontend

No full GPU profile. No general auto-launch.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Repo root (derived from this file)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Doctor import (for start gating)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from sovereign_doctor import _build_doctor_result, Summary, Status  # noqa: E402

# ---------------------------------------------------------------------------
# Runtime directories
# ---------------------------------------------------------------------------
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_FILE = RUNTIME_DIR / "launcher_state.json"

# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------
PORTS = {
    "frontend": 3000,
    "backend": 8000,
    "general": 8001,
    "coder": 8002,
    "vision": 8003,
}

# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------
PROFILES: Dict[str, Dict[str, Any]] = {
    "judge": {
        "model_servers": [],
        "backend": True,
        "frontend": True,
    },
    "vision": {
        "model_servers": [
            {
                "name": "vision",
                "model_id": "qwen-vision",
                "model_path": "models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
                "mmproj": "models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf",
                "chat_format": "qwen2-vl",
                "port": 8003,
                "n_gpu_layers": 99,
                "n_ctx": 2048,
            }
        ],
        "backend": True,
        "frontend": True,
    },
    "coder": {
        "model_servers": [
            {
                "name": "coder",
                "model_id": "qwen-coder",
                "model_path": "models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf",
                "port": 8002,
                "n_gpu_layers": 40,
                "n_ctx": 2048,
            }
        ],
        "backend": True,
        "frontend": True,
    },
}

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> Optional[Dict[str, Any]]:
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def clear_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()


# ---------------------------------------------------------------------------
# Process ownership helpers
# ---------------------------------------------------------------------------
def _is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _http_get(url: str, timeout: float = 2.0) -> Optional[int]:
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except Exception:
        return None


def _probe_service(port: int, path: str) -> Optional[str]:
    """Return 'free', 'expected', or 'conflict'."""
    if not _is_port_in_use(port):
        return "free"
    status = _http_get(f"http://127.0.0.1:{port}{path}")
    if status == 200:
        return "expected"
    return "conflict"


def _identify_service_on_port(port: int) -> Optional[str]:
    """Try to identify expected service on port via HTTP probe."""
    probes = {
        3000: "/",
        8000: "/api/system/health",
        8001: "/v1/models",
        8002: "/v1/models",
        8003: "/v1/models",
    }
    path = probes.get(port, "/")
    state = _probe_service(port, path)
    if state == "expected":
        return "expected"
    if state == "conflict":
        return "conflict"
    return None


def _kill_pid_tree(pid: int) -> None:
    """Kill a process tree on Windows. Only for launcher-owned PIDs."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Startup wait helpers
# ---------------------------------------------------------------------------
def _wait_for_port(port: int, path: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _http_get(f"http://127.0.0.1:{port}{path}", timeout=1.0) == 200:
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Service launchers
# ---------------------------------------------------------------------------
def _launch_backend(log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    log_file = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT / "backend"),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return proc


def _launch_frontend(log_path: Path) -> subprocess.Popen:
    cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "3000",
        "--strictPort",
    ]
    log_file = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT / "frontend"),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return proc


def _launch_model_server(
    cfg: Dict[str, Any],
    log_path: Path,
) -> subprocess.Popen:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "serve_model.py"),
        "--model-id",
        cfg["model_id"],
        "--model-path",
        str(REPO_ROOT / cfg["model_path"]),
        "--host",
        "127.0.0.1",
        "--port",
        str(cfg["port"]),
        "--n-gpu-layers",
        str(cfg["n_gpu_layers"]),
        "--n-ctx",
        str(cfg["n_ctx"]),
    ]
    if "mmproj" in cfg:
        cmd.extend(["--mmproj", str(REPO_ROOT / cfg["mmproj"])])
    if "chat_format" in cfg:
        cmd.extend(["--chat-format", cfg["chat_format"]])
    log_file = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return proc


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------
def _check_model_conflict(profile: str) -> Optional[str]:
    """Return conflict message if starting profile would conflict with live model."""
    if profile == "vision":
        if _probe_service(8002, "/v1/models") == "expected":
            return "Coder model server is already active on port 8002. Stop it before starting the vision competition profile on this VRAM-constrained host."
    elif profile == "coder":
        if _probe_service(8003, "/v1/models") == "expected":
            return "Vision model server is already active on port 8003. Stop it before starting the coder competition profile on this VRAM-constrained host."
    return None


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
def cmd_start(profile: str) -> int:
    profile = profile.lower()
    if profile not in PROFILES:
        print(f"Unknown profile: {profile}", file=sys.stderr)
        return 2

    doctor_result = _build_doctor_result(profile)
    if doctor_result.summary == Summary.BLOCKED:
        print("SOVEREIGN AI START BLOCKED")
        print()
        print(f"Profile:\n{profile}")
        print()
        print("Blocking checks:")
        for c in doctor_result.checks:
            if c.status == Status.FAIL and c.required:
                print(f"- {c.id}: {c.message}")
        print()
        print(f"Run:\npython scripts/sovereign.py doctor --profile {profile}")
        print()
        print("No process was started or modified.")
        return 1

    # Check for model conflicts
    conflict = _check_model_conflict(profile)
    if conflict:
        print(f"BLOCKED: {conflict}", file=sys.stderr)
        return 1

    # If state exists with same profile, try reuse first
    existing = load_state()
    if existing and existing.get("profile") == profile:
        print(f"Launcher state already exists for profile '{profile}'. Run 'stop' first or use 'status' to inspect.", file=sys.stderr)
        return 1

    _ensure_dirs()
    started_at = _utc_now_iso()
    processes: List[Dict[str, Any]] = []
    to_stop_on_rollback: List[subprocess.Popen] = []

    try:
        # Start model servers first for GPU profiles
        model_cfgs = PROFILES[profile].get("model_servers", [])
        for mcfg in model_cfgs:
            port = mcfg["port"]
            state = _probe_service(port, "/v1/models")
            if state == "expected":
                print(f"[INFO] {mcfg['name']} model server already running on port {port}")
                processes.append({
                    "name": mcfg["name"],
                    "pid": None,
                    "port": port,
                    "log_path": None,
                    "started_by_launcher": False,
                    "status": "REUSED",
                })
                continue
            if state == "conflict":
                print(f"[FAIL] Port {port} occupied by unrecognized process. Aborting.", file=sys.stderr)
                return 1

            log_name = f"{mcfg['name']}.log"
            log_path = LOG_DIR / log_name
            print(f"[INFO] Starting {mcfg['name']} model server on port {port}...")
            proc = _launch_model_server(mcfg, log_path)
            to_stop_on_rollback.append(proc)

            # Wait for model server
            model_timeout = 180.0
            if not _wait_for_port(port, "/v1/models", timeout=model_timeout):
                rc = proc.poll()
                if rc is not None:
                    print(f"[FAIL] {mcfg['name']} model server exited early (code {rc}). See {log_path}", file=sys.stderr)
                else:
                    print(f"[FAIL] {mcfg['name']} model server did not respond within {model_timeout}s. See {log_path}", file=sys.stderr)
                return 1

            processes.append({
                "name": mcfg["name"],
                "pid": proc.pid,
                "port": port,
                "log_path": str(log_path),
                "started_by_launcher": True,
                "status": "RUNNING",
            })
            print(f"[PASS] {mcfg['name']} model server online on port {port} (pid {proc.pid})")

        # Start backend
        if PROFILES[profile].get("backend"):
            port = PORTS["backend"]
            state = _probe_service(port, "/api/system/health")
            if state == "expected":
                print(f"[INFO] Backend already running on port {port}")
                processes.append({
                    "name": "backend",
                    "pid": None,
                    "port": port,
                    "log_path": None,
                    "started_by_launcher": False,
                    "status": "REUSED",
                })
            else:
                if state == "conflict":
                    print(f"[FAIL] Port {port} occupied by unrecognized process. Aborting.", file=sys.stderr)
                    return 1
                log_path = LOG_DIR / "backend.log"
                print(f"[INFO] Starting backend on port {port}...")
                proc = _launch_backend(log_path)
                to_stop_on_rollback.append(proc)
                if not _wait_for_port(port, "/api/system/health", timeout=60.0):
                    rc = proc.poll()
                    if rc is not None:
                        print(f"[FAIL] Backend exited early (code {rc}). See {log_path}", file=sys.stderr)
                    else:
                        print(f"[FAIL] Backend did not respond within 60s. See {log_path}", file=sys.stderr)
                    return 1
                processes.append({
                    "name": "backend",
                    "pid": proc.pid,
                    "port": port,
                    "log_path": str(log_path),
                    "started_by_launcher": True,
                    "status": "RUNNING",
                })
                print(f"[PASS] Backend online on port {port} (pid {proc.pid})")

        # Start frontend
        if PROFILES[profile].get("frontend"):
            port = PORTS["frontend"]
            state = _probe_service(port, "/")
            if state == "expected":
                print(f"[INFO] Frontend already running on port {port}")
                processes.append({
                    "name": "frontend",
                    "pid": None,
                    "port": port,
                    "log_path": None,
                    "started_by_launcher": False,
                    "status": "REUSED",
                })
            else:
                if state == "conflict":
                    print(f"[FAIL] Port {port} occupied by unrecognized process. Aborting.", file=sys.stderr)
                    return 1
                log_path = LOG_DIR / "frontend.log"
                print(f"[INFO] Starting frontend on port {port}...")
                proc = _launch_frontend(log_path)
                to_stop_on_rollback.append(proc)
                if not _wait_for_port(port, "/", timeout=45.0):
                    rc = proc.poll()
                    if rc is not None:
                        print(f"[FAIL] Frontend exited early (code {rc}). See {log_path}", file=sys.stderr)
                    else:
                        print(f"[FAIL] Frontend did not respond within 45s. See {log_path}", file=sys.stderr)
                    return 1
                processes.append({
                    "name": "frontend",
                    "pid": proc.pid,
                    "port": port,
                    "log_path": str(log_path),
                    "started_by_launcher": True,
                    "status": "RUNNING",
                })
                print(f"[PASS] Frontend online on port {port} (pid {proc.pid})")

        # Save state
        state = {
            "schema_version": 1,
            "profile": profile,
            "started_at": started_at,
            "processes": processes,
        }
        save_state(state)

        # Print summary
        _print_start_summary(profile, processes)
        return 0

    except Exception as e:
        print(f"[FAIL] Startup error: {e}", file=sys.stderr)
        # Rollback launcher-owned processes
        for proc in to_stop_on_rollback:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            for proc in to_stop_on_rollback:
                proc.wait(timeout=5)
        except Exception:
            pass
        return 1


def _print_start_summary(profile: str, processes: List[Dict[str, Any]]) -> None:
    def proc_status(name: str) -> str:
        for p in processes:
            if p["name"] == name:
                if p.get("started_by_launcher"):
                    return f"ONLINE — {name} :{p['port']}"
                else:
                    return f"REUSED — {name} :{p['port']}"
        return "NOT STARTED"

    print()
    print("=" * 62)
    print("SOVEREIGN AI — READY")
    print(f"Profile: {profile}")
    print("=" * 62)
    print()
    print(f"Frontend:\n  http://127.0.0.1:3000")
    print()
    print(f"Judge Mode:\n  http://127.0.0.1:3000/judge")
    print()
    print(f"Backend:\n  http://127.0.0.1:8000")
    print()
    print(f"Vision:\n  {proc_status('vision')}")
    print()
    print(f"Coder:\n  {proc_status('coder')}")
    print()
    print(f"General:\n  EXPECTED UNAVAILABLE — weights not provisioned")
    print()

    qdrant_ok = (REPO_ROOT / "data" / "rag" / "qdrant_db").exists()
    bm25_ok = (REPO_ROOT / "data" / "rag" / "bm25" / "bm25_index").exists()
    print(f"RAG:")
    print(f"  Qdrant embedded {'READY' if qdrant_ok else 'MISSING'}")
    print(f"  BM25 {'READY' if bm25_ok else 'MISSING'}")
    print()
    print(f"Logs:\n  {LOG_DIR}")
    print()
    print("=" * 62)
    print()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def cmd_status() -> int:
    state = load_state()
    print()
    if state:
        print(f"Profile: {state.get('profile', 'unknown')}")
        print()
        for p in state.get("processes", []):
            pid = p.get("pid")
            status = p.get("status", "UNKNOWN")
            name = p.get("name", "?")
            port = p.get("port", "?")
            owned = "launcher-owned" if p.get("started_by_launcher") else "reused/pre-existing"
            print(f"  {name}: {status} (port {port}, {owned})")
            if pid:
                print(f"    PID: {pid}")
    else:
        print("No launcher state recorded.")

    print()
    print("Local service probes:")
    service_ports = {
        "frontend": (3000, "/"),
        "backend": (8000, "/api/system/health"),
        "general": (8001, "/v1/models"),
        "coder": (8002, "/v1/models"),
        "vision": (8003, "/v1/models"),
    }
    for name, (port, path) in service_ports.items():
        probe = _probe_service(port, path)
        if probe == "expected":
            print(f"  {name}: RUNNING / reachable on port {port}")
        elif probe == "conflict":
            print(f"  {name}: CONFLICT on port {port}")
        else:
            print(f"  {name}: offline / not running on port {port}")

    print()
    return 0


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------
def cmd_stop() -> int:
    state = load_state()
    if not state:
        print("No launcher-owned Sovereign AI processes are recorded.")
        return 0

    processes = state.get("processes", [])
    if not processes:
        print("No launcher-owned Sovereign AI processes are recorded.")
        clear_state()
        return 0

    print("Stopping launcher-owned processes...")
    for p in processes:
        if not p.get("started_by_launcher"):
            print(f"  [SKIP] {p['name']} (pid {p.get('pid')}) — not launcher-owned")
            continue
        pid = p.get("pid")
        name = p.get("name", "?")
        if pid:
            print(f"  [STOP] {name} (pid {pid})")
            _kill_pid_tree(pid)
        else:
            print(f"  [SKIP] {name} — no PID recorded")

    # Brief verification
    time.sleep(1.0)
    still_running = []
    for p in processes:
        if not p.get("started_by_launcher"):
            continue
        pid = p.get("pid")
        port = p.get("port")
        if pid and _is_port_in_use(port):
            still_running.append(p["name"])

    if still_running:
        print(f"[WARN] Ports still in use after stop: {', '.join(still_running)}", file=sys.stderr)

    clear_state()
    print("Launcher state cleared.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sovereign AI Competition Launcher",
    )
    sub = parser.add_subparsers(dest="command")

    doc_p = sub.add_parser("doctor", help="Run system doctor")
    doc_p.add_argument("--profile", required=True, choices=["judge", "vision", "coder"])
    doc_p.add_argument("--json", action="store_true")

    start_p = sub.add_parser("start", help="Start a competition profile")
    start_p.add_argument("--profile", required=True, choices=["judge", "vision", "coder"])

    sub.add_parser("status", help="Show launcher status")
    sub.add_parser("stop", help="Stop launcher-owned processes")

    args = parser.parse_args()

    if args.command == "doctor":
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from sovereign_doctor import run_doctor
        return run_doctor(args.profile, json_output=args.json)

    if args.command == "start":
        return cmd_start(args.profile)

    if args.command == "status":
        return cmd_status()

    if args.command == "stop":
        return cmd_stop()

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
