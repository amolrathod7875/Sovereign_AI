"""Governance package: append-only receipt hash chain.

Phase 15C1 adds a tamper-evident SHA256-linked chain across terminal
Sovereignty Receipts. Each new chain entry references the previous chain
entry's hash, forming a cryptographic linked list.

This module is intentionally isolated from Phase 15B receipt payload
semantics. The receipt payload and receipt_sha256 remain unchanged.
Chain append occurs inside the existing terminal-review transaction so
approval, receipt, and chain entry commit atomically.

Limitations:
- The chain is tamper-evident, not tamper-proof.
- No external trust anchor or digital signature exists.
- An attacker with unrestricted SQLite write access could rewrite the
  entire history and recompute the chain from genesis.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


CHAIN_SCHEMA_VERSION = "1.0"
GENESIS_PREVIOUS_HASH = "0" * 64


class ReceiptChainNotFoundError(Exception):
    """Raised when a chain entry or the chain head does not exist."""


class ReceiptChainConflictError(Exception):
    """Raised when a chain append conflicts with an existing entry."""


class ReceiptChainIntegrityError(Exception):
    """Raised when stored chain integrity is violated."""


@dataclass(frozen=True)
class ReceiptChainEntry:
    sequence_no: int
    run_id: str
    receipt_id: str
    receipt_sha256: str
    approval_status: str
    linked_at: str
    previous_chain_sha256: str
    chain_sha256: str


def _canonicalize_chain_material(material: dict) -> bytes:
    return json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _compute_chain_sha256(material: dict) -> str:
    return hashlib.sha256(_canonicalize_chain_material(material)).hexdigest()


def _build_chain_material(
    sequence_no: int,
    run_id: str,
    receipt_id: str,
    receipt_sha256: str,
    approval_status: str,
    linked_at: str,
    previous_chain_sha256: str,
) -> dict:
    return {
        "chain_schema_version": CHAIN_SCHEMA_VERSION,
        "sequence_no": sequence_no,
        "run_id": run_id,
        "receipt_id": receipt_id,
        "receipt_sha256": receipt_sha256,
        "approval_status": approval_status,
        "linked_at": linked_at,
        "previous_chain_sha256": previous_chain_sha256,
    }


class ReceiptChainService:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is not None:
            self.db_path = db_path
        else:
            from governance.approval import ApprovalService

            self.db_path = ApprovalService().db_path

    def _connect(self) -> sqlite3.Connection:
        import os
        from pathlib import Path

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.isolation_level = None
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipt_chain (
                sequence_no INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                receipt_id TEXT NOT NULL UNIQUE,
                receipt_sha256 TEXT NOT NULL,
                approval_status TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                previous_chain_sha256 TEXT NOT NULL,
                chain_sha256 TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chain_sequence ON receipt_chain(sequence_no)"
        )

    def _ensure_schema_standalone(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)

    def _append_in_transaction(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        receipt_id: str,
        receipt_sha256: str,
        approval_status: str,
        linked_at: str,
    ) -> ReceiptChainEntry:
        self._ensure_schema(conn)

        cur = conn.execute(
            "SELECT receipt_id FROM sovereignty_receipts WHERE run_id = ?",
            (run_id,),
        )
        receipt_row = cur.fetchone()
        if not receipt_row:
            raise ReceiptChainConflictError(
                f"receipt not found for run_id during chain append: {run_id}"
            )

        cur = conn.execute(
            "SELECT run_id FROM receipt_chain WHERE run_id = ?",
            (run_id,),
        )
        if cur.fetchone():
            raise ReceiptChainConflictError(
                f"chain entry already exists for run_id: {run_id}"
            )

        cur = conn.execute(
            "SELECT sequence_no, chain_sha256 FROM receipt_chain ORDER BY sequence_no DESC LIMIT 1"
        )
        head = cur.fetchone()
        if head is None:
            next_sequence = 1
            previous = GENESIS_PREVIOUS_HASH
        else:
            next_sequence = head["sequence_no"] + 1
            previous = head["chain_sha256"]

        material = _build_chain_material(
            sequence_no=next_sequence,
            run_id=run_id,
            receipt_id=receipt_id,
            receipt_sha256=receipt_sha256,
            approval_status=approval_status,
            linked_at=linked_at,
            previous_chain_sha256=previous,
        )
        chain_sha256 = _compute_chain_sha256(material)

        conn.execute(
            """
            INSERT INTO receipt_chain (
                sequence_no, run_id, receipt_id, receipt_sha256,
                approval_status, linked_at, previous_chain_sha256, chain_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                next_sequence,
                run_id,
                receipt_id,
                receipt_sha256,
                approval_status,
                linked_at,
                previous,
                chain_sha256,
            ),
        )
        return ReceiptChainEntry(
            sequence_no=next_sequence,
            run_id=run_id,
            receipt_id=receipt_id,
            receipt_sha256=receipt_sha256,
            approval_status=approval_status,
            linked_at=linked_at,
            previous_chain_sha256=previous,
            chain_sha256=chain_sha256,
        )

    def get_entry(self, run_id: str) -> ReceiptChainEntry:
        self._ensure_schema_standalone()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM receipt_chain WHERE run_id = ?",
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ReceiptChainNotFoundError(
                    f"chain entry not found for run_id: {run_id}"
                )
            return ReceiptChainEntry(
                sequence_no=row["sequence_no"],
                run_id=row["run_id"],
                receipt_id=row["receipt_id"],
                receipt_sha256=row["receipt_sha256"],
                approval_status=row["approval_status"],
                linked_at=row["linked_at"],
                previous_chain_sha256=row["previous_chain_sha256"],
                chain_sha256=row["chain_sha256"],
            )

    def list_entries(self) -> List[ReceiptChainEntry]:
        self._ensure_schema_standalone()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM receipt_chain ORDER BY sequence_no ASC"
            )
            return [
                ReceiptChainEntry(
                    sequence_no=row["sequence_no"],
                    run_id=row["run_id"],
                    receipt_id=row["receipt_id"],
                    receipt_sha256=row["receipt_sha256"],
                    approval_status=row["approval_status"],
                    linked_at=row["linked_at"],
                    previous_chain_sha256=row["previous_chain_sha256"],
                    chain_sha256=row["chain_sha256"],
                )
                for row in cur.fetchall()
            ]

    def get_head(self) -> Optional[dict]:
        self._ensure_schema_standalone()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT sequence_no, chain_sha256, run_id FROM receipt_chain ORDER BY sequence_no DESC LIMIT 1"
            )
            head_row = cur.fetchone()
            cur = conn.execute("SELECT COUNT(*) as cnt FROM receipt_chain")
            count_row = cur.fetchone()
            cnt = count_row["cnt"] if count_row else 0
            if cnt == 0 or head_row is None:
                return {
                    "entry_count": 0,
                    "head_sequence": None,
                    "head_chain_sha256": None,
                    "head_run_id": None,
                }
            return {
                "entry_count": cnt,
                "head_sequence": head_row["sequence_no"],
                "head_chain_sha256": head_row["chain_sha256"],
                "head_run_id": head_row["run_id"],
            }

    def verify_chain(self) -> dict:
        entries = self.list_entries()
        entry_count = len(entries)
        checks: dict = {
            "sequence_contiguous": True,
            "genesis_valid": True,
            "links_valid": True,
            "entry_hashes_valid": True,
            "receipt_bindings_valid": True,
            "receipt_self_hashes_valid": True,
            "duplicate_runs_absent": True,
            "unlinked_receipts_absent": True,
        }
        violations: list = []

        if entry_count == 0:
            with self._connect() as conn:
                try:
                    unlinked_cur = conn.execute(
                        "SELECT run_id FROM sovereignty_receipts WHERE run_id NOT IN (SELECT run_id FROM receipt_chain)"
                    )
                    unlinked_rows = unlinked_cur.fetchall()
                except sqlite3.OperationalError:
                    unlinked_rows = []
            if unlinked_rows:
                checks["unlinked_receipts_absent"] = False
                for row in unlinked_rows:
                    violations.append(f"unlinked legacy receipt found: {row['run_id']}")
            all_valid = all(checks.values()) and len(violations) == 0
            status = "VALID" if all_valid else "INVALID"
            return {
                "valid": all_valid,
                "status": status,
                "entry_count": 0,
                "head_sequence": None,
                "head_chain_sha256": None,
                "checks": checks,
                "violations": violations,
            }

        head_sequence = entries[-1].sequence_no
        head_chain_sha256 = entries[-1].chain_sha256

        seen_run_ids = set()
        seen_receipt_ids = set()

        for i, entry in enumerate(entries):
            expected_seq = i + 1
            if entry.sequence_no != expected_seq:
                checks["sequence_contiguous"] = False
                violations.append(
                    f"sequence gap or reorder at position {i}: expected {expected_seq}, got {entry.sequence_no}"
                )

            if entry.run_id in seen_run_ids:
                checks["duplicate_runs_absent"] = False
                violations.append(f"duplicate run_id in chain: {entry.run_id}")
            seen_run_ids.add(entry.run_id)

            if entry.receipt_id in seen_receipt_ids:
                checks["duplicate_runs_absent"] = False
                violations.append(f"duplicate receipt_id in chain: {entry.receipt_id}")
            seen_receipt_ids.add(entry.receipt_id)

            if i == 0:
                if entry.previous_chain_sha256 != GENESIS_PREVIOUS_HASH:
                    checks["genesis_valid"] = False
                    violations.append(
                        f"genesis previous hash invalid: {entry.previous_chain_sha256}"
                    )
            else:
                prev = entries[i - 1]
                if entry.previous_chain_sha256 != prev.chain_sha256:
                    checks["links_valid"] = False
                    violations.append(
                        f"chain link broken at sequence {entry.sequence_no}: "
                        f"previous={entry.previous_chain_sha256}, expected={prev.chain_sha256}"
                    )

            material = _build_chain_material(
                sequence_no=entry.sequence_no,
                run_id=entry.run_id,
                receipt_id=entry.receipt_id,
                receipt_sha256=entry.receipt_sha256,
                approval_status=entry.approval_status,
                linked_at=entry.linked_at,
                previous_chain_sha256=entry.previous_chain_sha256,
            )
            recomputed = _compute_chain_sha256(material)
            if recomputed != entry.chain_sha256:
                checks["entry_hashes_valid"] = False
                violations.append(
                    f"chain hash mismatch at sequence {entry.sequence_no}: "
                    f"stored={entry.chain_sha256}, recomputed={recomputed}"
                )

        with self._connect() as conn:
            for entry in entries:
                cur = conn.execute(
                    "SELECT receipt_id, approval_status, created_at, receipt_sha256, payload_json FROM sovereignty_receipts WHERE run_id = ?",
                    (entry.run_id,),
                )
                receipt_row = cur.fetchone()
                if not receipt_row:
                    checks["receipt_bindings_valid"] = False
                    violations.append(
                        f"referenced receipt missing for run_id: {entry.run_id}"
                    )
                    continue

                if receipt_row["receipt_id"] != entry.receipt_id:
                    checks["receipt_bindings_valid"] = False
                    violations.append(
                        f"receipt_id mismatch for {entry.run_id}: chain={entry.receipt_id}, db={receipt_row['receipt_id']}"
                    )

                if receipt_row["approval_status"] != entry.approval_status:
                    checks["receipt_bindings_valid"] = False
                    violations.append(
                        f"approval_status mismatch for {entry.run_id}: chain={entry.approval_status}, db={receipt_row['approval_status']}"
                    )

                if receipt_row["created_at"] != entry.linked_at:
                    checks["receipt_bindings_valid"] = False
                    violations.append(
                        f"linked_at mismatch for {entry.run_id}: chain={entry.linked_at}, db={receipt_row['created_at']}"
                    )

                if receipt_row["receipt_sha256"] != entry.receipt_sha256:
                    checks["receipt_bindings_valid"] = False
                    violations.append(
                        f"receipt_sha256 mismatch for {entry.run_id}: chain={entry.receipt_sha256}, db={receipt_row['receipt_sha256']}"
                    )

                try:
                    payload = json.loads(receipt_row["payload_json"])
                except Exception:
                    checks["receipt_self_hashes_valid"] = False
                    violations.append(
                        f"receipt payload JSON decode failed for {entry.run_id}"
                    )
                    continue

                canonical = _canonicalize_chain_material(payload)
                recomputed_receipt_sha = hashlib.sha256(canonical).hexdigest()
                if recomputed_receipt_sha != receipt_row["receipt_sha256"]:
                    checks["receipt_self_hashes_valid"] = False
                    violations.append(
                        f"receipt self-hash invalid for {entry.run_id}"
                    )

        unlinked_cur = conn.execute(
            "SELECT run_id FROM sovereignty_receipts WHERE run_id NOT IN (SELECT run_id FROM receipt_chain)"
        )
        unlinked_rows = unlinked_cur.fetchall()
        if unlinked_rows:
            checks["unlinked_receipts_absent"] = False
            for row in unlinked_rows:
                violations.append(f"unlinked legacy receipt found: {row['run_id']}")

        all_valid = all(checks.values()) and len(violations) == 0
        status = "VALID" if all_valid else "INVALID"
        return {
            "valid": all_valid,
            "status": status,
            "entry_count": entry_count,
            "head_sequence": head_sequence,
            "head_chain_sha256": head_chain_sha256,
            "checks": checks,
            "violations": violations,
        }
