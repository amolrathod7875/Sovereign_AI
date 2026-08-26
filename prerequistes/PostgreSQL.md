# PostgreSQL --- Relational Database --- Complete Reference

> A plain-English, friend-explainer guide to the **PostgreSQL** relational database used in the Sovereign AI workbench (PS 26117).
> `Better_plan.md` §2 lists: *"Relational DB: PostgreSQL"* (users, tasks, executions, audit records). Sources: official PostgreSQL documentation (postgresql.org) and Wikipedia.

---

## 0. Words & Terms Your Team Mates Should Know (Read This First)

PostgreSQL is the **system of record** — it stores structured metadata and audit logs (not the document text/vectors, those go to Qdrant). These terms explain it.

| Term | Plain-English Meaning |
|---|---|
| **PostgreSQL / Postgres** | A free, open-source relational database (the "source of truth" for structured data). |
| **RDBMS / ORDBMS** | Relational (tables of rows/columns) + object features. Postgres is "object-relational". |
| **Table** | A grid of data (like a spreadsheet sheet) with rows and columns. |
| **Row / Record** | One entry in a table (e.g., one execution). |
| **Column / Field** | One attribute of a record (e.g., status, started_at). |
| **SQL** | The standard language to query/insert/update data (`SELECT`, `INSERT`, etc.). |
| **ACID** | Guarantees: Atomic, Consistent, Isolated, Durable — safe transactions even under failure. |
| **MVCC** | Multi-Version Concurrency Control — readers don't block writers; each transaction sees a snapshot. |
| **WAL** | Write-Ahead Log — changes are logged before applied, enabling crash recovery & replication. |
| **Index** | A lookup structure (B-tree, GIN, etc.) that makes searches fast. |
| **Primary Key** | A unique ID for each row. |
| **Foreign Key** | A link from one table to another (e.g., execution → conversation). |
| **Metadata** | Data *about* data (e.g., who ran a task, when, with which model). |
| **Audit record** | A log entry proving what happened (for compliance/safety). |
| **Replication** | Copying data to a standby server for failover/read scaling. |
| **Docker image `postgres`** | The official way we run Postgres in a container. |
| **RAG / Qdrant** | The vector search side; Postgres is *not* for embeddings (Qdrant is). |
| **PS 26117** | The internal project spec this tool is used for. |

> Tip for teammates: scan this table first whenever you hit an unknown word.

---

## 1. TL;DR (for you and your friends)

- **What it is:** A powerful, open-source **relational database** that stores our structured data: users, tasks, executions, steps, artifacts, models, and audit/network logs.
- **Why it's in our stack:** `Better_plan.md` §2/§14 uses **PostgreSQL** as the system of record for metadata + audit. Embeddings go to Qdrant; structured operational data goes here.
- **Who made it:** The **PostgreSQL Global Development Group** (worldwide community), originally from UC Berkeley's POSTGRES project (led by Prof. Michael Stonebraker).
- **License:** **PostgreSQL License** — permissive (BSD-like), free for any use, including commercial.
- **Why Postgres:** ACID-safe, reliable, extensible, runs anywhere (including in Docker on our machine).
- **Sovereignty feature:** Self-hosted in Docker Compose; no cloud database, no external calls.

---

## 2. A. Who Owns It

| Attribute | Detail |
|---|---|
| **Owner / Maintainer** | **PostgreSQL Global Development Group** (community) |
| **Origin** | UC Berkeley POSTGRES project (1986), Prof. Michael Stonebraker |
| **First PostgreSQL release** | v6.0, 1997 (renamed from Postgres95 in 1996) |
| **Repository** | git.postgresql.org |
| **License** | **PostgreSQL License** (permissive, BSD-style) |
| **Written in** | C (with C++ for the LLVM/JIT parts) |
| **Stable release** | 18.x (2025); 19 in beta |

---

## 3. B. History — How It Evolved

```mermaid
timeline
    title PostgreSQL Timeline
    1986 : POSTGRES project begins at UC Berkeley
    1989 : POSTGRES v1 released
    1994 : SQL interpreter added → "Postgres95"
    1996 : Renamed PostgreSQL; v6.0 in 1997
    2001 : ACID compliance via MVCC
    2010s : Streaming replication, JSONB, extensions boom
    2025 : v18 (170/177 SQL:2023 core features)
```

Postgres is one of the most mature open-source databases (~40 years of lineage), known for reliability and extensibility — why it's the default choice for serious applications.

---

## 4. C. What It Does / Why We Need It

The AI models and Qdrant handle *understanding* and *similarity search*. Postgres handles **durable bookkeeping**: who asked what, which model ran, what steps executed, what artifact was produced, and a full audit trail.

```mermaid
flowchart LR
    APP["FastAPI Backend"] --> PG["PostgreSQL<br/>(metadata + audit)"]
    APP --> QD["Qdrant (vectors)"]
    APP --> FS["Local filesystem (artifacts)"]
    PG --> AUD["Audit log / trace records"]
```

Division of labor in our stack:
- **Qdrant** → document embeddings & similarity search.
- **PostgreSQL** → users, conversations, tasks, executions, steps, artifacts, models, network events.
- **Local filesystem / MinIO** → the actual artifact files (PDF/XLSX/PPTX/code).

---

## 5. D. Architecture & Internals

### 5.1 Layered Architecture

```mermaid
graph TD
    CLIENT["Client / Backend (libpq / SQLAlchemy)"] --> SQL["SQL Layer<br/>(Parser → Planner → Executor)"]
    SQL --> MVCC["Transaction manager (MVCC, isolation levels)"]
    MVCC --> STORE["Storage: Heap + Indexes<br/>(B-tree, GIN, GiST, BRIN)"]
    MVCC --> WAL["WAL (Write-Ahead Log)"]
    WAL --> REPL["Replication (async / sync / logical)"]
    WAL --> PITR["Point-in-time recovery"]
```

### 5.2 Core Mechanisms

| Mechanism | What it gives us |
|---|---|
| **ACID + MVCC** | Safe concurrent transactions; readers don't block writers; crash-safe |
| **WAL** | Durability + replication + point-in-time recovery |
| **Indexes** | B-tree (default), GIN (JSON/arrays), GiST, SP-GiST, BRIN, Bloom — fast lookups |
| **JSON/JSONB** | Store semi-structured data (e.g., step metadata) natively |
| **Extensibility** | Custom types, functions, FDWs, procedural languages (PL/pgSQL, Python…) |
| **Full-text search** | Optional in-DB text search (we mostly use Qdrant, but available) |

### 5.3 Our Data Model (from `Better_plan.md` §14)

Postgres tables back the whole agent lifecycle:

| Entity | Key fields |
|---|---|
| User | `id`, `role`, `created_at` |
| Conversation | `id`, `user_id`, `title`, `created_at` |
| Message | `id`, `conversation_id`, `role`, `content` |
| Document | `id`, `filename`, `mime_type`, `size`, `checksum`, `doc_type`, `status` |
| DocumentChunk | `id`, `document_id`, `page`, `section`, `text`, `metadata`, `qdrant_point_id` |
| AgentExecution | `id`, `conversation_id`, `task_type`, `status`, `started_at`, `completed_at` |
| ExecutionStep | `id`, `execution_id`, `step_index`, `action`, `model`, `tool`, `status`, `duration`, `metadata` |
| Artifact | `id`, `execution_id`, `filename`, `mime_type`, `path`, `checksum` |
| Model | `id`, `name`, `endpoint`, `capabilities`, `context_length`, `status` |
| **NetworkEvent** | `id`, `timestamp`, `destination_host`, `destination_port`, `action`, `execution_id` |

These give us the **execution trace** and **audit log** required by §13 and §12.2.

---

## 6. Deployment in the Sovereign AI Stack

In `Better_plan.md` §2/§17, Postgres is a service in our Docker Compose stack.

```mermaid
flowchart TD
    BE["FastAPI Backend (SQLAlchemy)"] --> PG["postgres container<br/>(Docker Compose)"]
    PG --> TBL["Tables: users, conversations,<br/>executions, steps, artifacts,<br/>models, network_events"]
    PG --> AUD["Audit + trace queries"]
    AUD --> DASH["Dashboard / Execution Trace UI"]
```

### 6.1 Operational Notes

- Image: `postgres` (official Docker image) in `docker-compose.yml`.
- Persist data via a Docker **volume** so it survives container restarts.
- Use a local connection string (e.g., `postgresql://user:pass@postgres:5432/sovereign`).
- Back it up with `pg_dump` / WAL archiving if needed.
- All local → network monitor shows `External AI API calls: 0`.

### 6.2 Why It Satisfies Sovereignty

- Self-hosted; **no cloud database** → meets "keep confidential info inside the boundary" (§12).
- Holds audit records locally, supporting the audit-log requirement (§12.2).
- Open-source license with no vendor lock-in.

---

## 7. Quick Facts Card (shareable)

```
Tool:        PostgreSQL (relational DB)
Owner:       PostgreSQL Global Development Group
License:     PostgreSQL License (permissive, BSD-style)
Type:        Object-relational (ORDBMS), ACID, MVCC
Language:    C
Role in PS:  System of record — metadata + audit (not vectors)
Data:        users, tasks, executions, steps, artifacts, models, network events
Deploy:      Docker Compose (postgres image, local volume)
Sovereign:   Fully local; no cloud DB; open-source
```

---

## 8. References

- Official docs: https://www.postgresql.org/docs/current/intro-whatis.html
- History: https://www.postgresql.org/docs/current/history.html
- Internals overview: https://www.postgresql.org/docs/current/overview.html
- About: https://www.postgresql.org/about/
