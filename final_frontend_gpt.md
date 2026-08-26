# Sovereign AI --- Final Frontend Specification

## `final_frontend.md`

> **Purpose:** The final frontend master specification for Sovereign AI
> PS 26117.
>
> This document combines the strongest implementation details from
> `frontend.md` with the strongest UX, architecture, security,
> observability, and demo principles from `frontend_gpt.md`.
>
> **Source basis:** Both uploaded frontend specifications, aligned with
> the existing Sovereign AI backend architecture and PS requirements.
> The frontend remains a presentation/interaction layer; FastAPI remains
> the application/security boundary. fileciteturn5file12
> fileciteturn5file5

------------------------------------------------------------------------

# 1. Product Vision

Sovereign AI is not a generic chatbot.

The frontend should feel like:

``` text
Claude/Codex-style interaction
        +
Enterprise document workbench
        +
Engineering analysis console
        +
Agent execution monitor
        +
Sovereign infrastructure dashboard
```

The product should communicate three ideas continuously:

``` text
LOCAL
PRIVATE
AUDITABLE
```

The judge should understand the architecture by watching the UI rather
than needing a long explanation.

The core principle is:

> **Do not try to prove intelligence with visual effects. Prove it
> through visible execution.**

The user should be able to see:

``` text
WHAT I ASKED
      ↓
TASK CLASSIFICATION
      ↓
MODEL SELECTED
      ↓
LOCAL KNOWLEDGE USED
      ↓
TOOLS EXECUTED
      ↓
EVIDENCE FOUND
      ↓
RESULT VERIFIED
      ↓
ARTIFACT GENERATED
      ↓
EXTERNAL CALLS: 0
```

This follows the existing backend/demo principle that the execution
trace should expose model selection, retrieval, tool calls, evidence,
artifacts, and local-only status. fileciteturn5file19

------------------------------------------------------------------------

# 2. UX Principles

## 2.1 Sovereignty First

The global application shell must always expose:

``` text
● SOVEREIGN MODE
LOCAL / AIR-GAPPED
External AI Calls: 0
```

The indicator opens the Network Monitor.

------------------------------------------------------------------------

## 2.2 Chat Is Only One Part

The product exposes:

-   AI Workbench
-   Knowledge Base
-   Executions
-   Model Registry
-   Artifacts
-   Network Monitor
-   System Health

The result should feel like an **AI workbench**, not a chat page.

------------------------------------------------------------------------

## 2.3 Evidence Over Hidden Reasoning

Never expose private chain-of-thought.

Instead expose safe execution evidence:

``` text
✓ Task classified
✓ Model selected
✓ OCR completed
✓ RAG retrieved evidence
✓ Tool executed
✓ Result verified
✓ Artifact generated
✓ External calls: 0
```

------------------------------------------------------------------------

## 2.4 Progressive Disclosure

Keep the default experience clean.

``` text
Answer
  ↓
Sources
  ↓
Execution trace
  ↓
Tool details
  ↓
Technical metadata
```

Advanced users and judges can inspect more detail without overwhelming
normal users.

------------------------------------------------------------------------

## 2.5 Local by Default

The frontend never talks directly to infrastructure components.

Browser:

``` text
React
  ↓
FastAPI
```

Not:

``` text
React → Qdrant
React → PostgreSQL
React → vLLM
React → Piston
```

FastAPI remains the application boundary.

------------------------------------------------------------------------

# 3. Design Direction

## 3.1 Visual Identity

Style:

``` text
Enterprise
Industrial
Technical
Minimal
Trustworthy
Data-dense
```

Avoid:

-   Cartoon AI graphics
-   Huge animated AI brains
-   Excessive gradients
-   Consumer-chat aesthetics
-   Decorative animation
-   Unnecessary visual noise

Prefer:

-   Strong hierarchy
-   Dense but readable information
-   Technical metadata
-   Clear status indicators
-   Subtle borders
-   Monospace for IDs/logs/code
-   Calm motion

------------------------------------------------------------------------

# 4. Design System

## 4.1 Color Palette

Use the implementation palette established in the frontend
specification:

  Role                   Color           Hex
  ---------------------- --------------- -----------
  Background Primary     Deep Navy       `#0D1117`
  Background Secondary   Dark Slate      `#161B22`
  Background Tertiary    Charcoal        `#21262D`
  Border                 Subtle Gray     `#30363D`
  Text Primary           Off-White       `#E6EDF3`
  Text Secondary         Muted Gray      `#8B949E`
  Primary Accent         Electric Blue   `#58A6FF`
  Success                Emerald         `#3FB950`
  Warning                Amber           `#D29922`
  Danger                 Coral Red       `#F85149`
  Sovereignty            Teal/Green      `#2EA043`

------------------------------------------------------------------------

## 4.2 Semantic Colors

``` text
Green  → healthy / successful / local
Blue   → processing / informational
Amber  → warning / pending / standby
Red    → failed / blocked / security event
Gray   → inactive / offline
```

------------------------------------------------------------------------

## 4.3 Typography

Primary UI:

``` text
Inter
```

Technical content:

``` text
JetBrains Mono
```

Use monospace for:

-   Execution IDs
-   Document IDs
-   API paths
-   Model endpoints
-   Network events
-   Code
-   Logs
-   Checksums

------------------------------------------------------------------------

## 4.4 Spacing

Base:

``` text
4px
```

Typical:

``` text
Component padding: 16px
Section gap: 24px
Card radius: 8px
Button radius: 6px
```

------------------------------------------------------------------------

## 4.5 Motion

Motion should communicate state, not decorate the application.

``` text
Step transition: 200ms
Loading pulse: subtle
Toast: 300ms
Completion check: 150ms
```

------------------------------------------------------------------------

# 5. Global Application Shell

``` text
┌─────────────────────────────────────────────────────────────────────┐
│ SOVEREIGN AI                         ● LOCAL / AIR-GAPPED     👤     │
├───────────────┬─────────────────────────────────────────────────────┤
│               │                                                     │
│ ◉ Workbench   │                                                     │
│               │                                                     │
│ ▣ Knowledge   │                    MAIN CONTENT                     │
│   Base        │                                                     │
│               │                                                     │
│ ◇ Executions  │                                                     │
│               │                                                     │
│ ◎ Models      │                                                     │
│               │                                                     │
│ □ Artifacts   │                                                     │
│               │                                                     │
│ ◈ Network     │                                                     │
│               │                                                     │
│ ⚙ System      │                                                     │
│               │                                                     │
├───────────────┤                                                     │
│ GPU           │                                                     │
│ ███████░ 72%  │                                                     │
│               │                                                     │
│ vLLM ●        │                                                     │
│ Qdrant ●      │                                                     │
│ PostgreSQL ●  │                                                     │
│ Piston ●      │                                                     │
└───────────────┴─────────────────────────────────────────────────────┘
```

## Sidebar

Primary navigation:

1.  AI Workbench
2.  Knowledge Base
3.  Executions
4.  Model Registry
5.  Artifacts
6.  Network Monitor
7.  System

The sidebar contains compact service health.

------------------------------------------------------------------------

# 6. Global Header

## Left

``` text
SOVEREIGN AI
PS 26117
```

## Center

Current workspace:

``` text
AI Workbench
```

## Right

``` text
● LOCAL / AIR-GAPPED
GPU: 72%
Models: 3
```

The sovereignty badge is always visible.

------------------------------------------------------------------------

# 7. Dashboard

The Dashboard answers:

-   Is the system healthy?
-   Is it local?
-   Which models are available?
-   What recently executed?
-   What artifacts were generated?
-   Are there network events?

``` text
┌────────────────────────────────────────────────────────────────────┐
│ Dashboard                                                          │
│ Local Enterprise AI Workbench                                     │
├────────────────┬────────────────┬──────────────────────────────────┤
│ SOVEREIGN      │ GPU            │ SERVICES                         │
│ ● ACTIVE       │ ███████░ 72%   │ vLLM General     ●              │
│ External Calls │ 4.8 / 6 GB     │ vLLM Coder       ●              │
│      0         │ 61°C           │ Qdrant           ●              │
│                │                │ PostgreSQL       ●              │
│                │                │ Piston           ●              │
├────────────────┴────────────────┴──────────────────────────────────┤
│ RECENT ACTIVITY                                                    │
│                                                                    │
│ ✓ Inspection report analyzed                    2 min ago         │
│ ✓ approval_note.docx generated                  2 min ago         │
│ ✓ CSV analysis verified                          8 min ago         │
│ ✓ Engineering image analyzed                    21 min ago        │
├──────────────────────────────────────┬─────────────────────────────┤
│ QUICK ACTIONS                        │ NETWORK STATUS              │
│ + New AI Task                        │ External AI calls: 0        │
│ + Upload Document                    │ Blocked attempts: 3         │
│ + Search Knowledge Base              │ Local traffic: healthy      │
└──────────────────────────────────────┴─────────────────────────────┘
```

------------------------------------------------------------------------

# 8. AI Workbench

This is the primary screen.

It should feel familiar to users of Claude/Codex while exposing agent
execution.

``` text
┌────────────────────────────────────────────────────────────────────┐
│ AI WORKBENCH                                                       │
├───────────────┬───────────────────────────────────┬────────────────┤
│ CONVERSATIONS │ ACTIVE SESSION                    │ TASK CONTEXT   │
│               │                                   │                │
│ + New Chat    │ User                              │ Files          │
│               │ Analyze inspection report...      │ report.pdf     │
│ Inspection    │                                   │                │
│ Report        │ Assistant                         │ Knowledge      │
│ Analysis      │ I found 3 critical findings...   │ ✓ SOP          │
│               │                                   │ ✓ Manual       │
│ CSV Analysis  │ Sources                           │                │
│               │ [SOP p.17] [SOP p.23]             │ Model          │
│ Drawing Review│                                   │ Auto            │
│               │ Artifact                          │ Task           │
│ Vendor Search │ approval_note.docx               │ DOCUMENT_ANALYSIS│
│               │ [Open] [Download]                 │                │
├───────────────┴───────────────────────────────────┴────────────────┤
│ EXECUTION TRACE                                                     │
│ ✓ Task classified → ✓ Model → ✓ OCR → ✓ RAG → ✓ DOCX              │
│ External calls: 0                                                   │
├─────────────────────────────────────────────────────────────────────┤
│ + Attach file     Ask anything...                           [Send] │
└─────────────────────────────────────────────────────────────────────┘
```

## Composer

Supports:

-   Text
-   File attachment
-   Drag-and-drop
-   Task mode
-   Optional model preference
-   Send/cancel
-   Streaming

Default:

``` text
Task: Auto
Model: Auto
Knowledge Base: Auto
Tools: Auto
```

The user should not normally have to choose the model.

------------------------------------------------------------------------

# 9. File Upload Experience

Supported:

``` text
PDF
DOCX
XLSX
CSV
PPTX
PNG/JPG
EML/MSG
```

Upload card:

``` text
┌───────────────────────────────────────────────┐
│                                               │
│            Drop files here                    │
│                                               │
│       or click to browse                     │
│                                               │
│ PDF • DOCX • XLSX • CSV • PPTX • IMAGE        │
│ EML • MSG                                     │
│                                               │
│             Max 50 MB                         │
└───────────────────────────────────────────────┘
```

After upload:

``` text
inspection_report.pdf

✓ Uploaded
→ Validating
→ Detecting document type
→ OCR required
→ Ingestion queued
```

The frontend displays processing state; the backend decides how the
document is processed.

------------------------------------------------------------------------

# 10. Knowledge Base

The Knowledge Base is the organization's private memory.

``` text
┌────────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE BASE                                      [+ Add Files]  │
├────────────────────────────────────────────────────────────────────┤
│ Search knowledge...                               Filter ▼         │
├───────────────┬──────────────┬───────────┬───────────┬────────────┤
│ Document      │ Type         │ Status    │ Chunks    │ Updated    │
├───────────────┼──────────────┼───────────┼───────────┼────────────┤
│ Maintenance   │ SOP          │ ● Ready   │ 384       │ Today      │
│ Safety Manual │ Manual       │ ● Ready   │ 512       │ Yesterday  │
│ Inspection    │ Report       │ ● Ready   │ 96        │ Today      │
│ Vendor Email  │ Correspond.  │ ● Ready   │ 41        │ Today      │
└───────────────┴──────────────┴───────────┴───────────┴────────────┘
```

Document details:

``` text
Filename
Type
Size
Checksum
Pages
Chunks
Ingestion version
Created
Status

[View extracted content]
[View metadata]
[Re-index]
```

------------------------------------------------------------------------

# 11. Knowledge Search

``` text
┌───────────────────────────────────────────────────────────────┐
│ KNOWLEDGE SEARCH                                              │
├───────────────────────────────────────────────────────────────┤
│ What does the maintenance SOP say about pump vibration?       │
│                                                     [Search]  │
├───────────────────────────────────────────────────────────────┤
│ RESULTS                                                       │
│                                                               │
│ 1. Maintenance_SOP.pdf — Page 17                             │
│    Relevance: 0.94                                            │
│                                                               │
│ 2. Maintenance_SOP.pdf — Page 23                             │
│    Relevance: 0.88                                            │
│                                                               │
│ 3. Inspection_Report.pdf — Page 4                            │
│    Relevance: 0.81                                            │
└───────────────────────────────────────────────────────────────┘
```

Advanced debug:

``` text
Dense results
BM25 results
RRF score
Reranker score
Final ranking
```

------------------------------------------------------------------------

# 12. Execution Trace

This is a core product feature.

The trace shows **what the system did**, not private chain-of-thought.

``` text
EXECUTION #EX-1042

Task:
Analyze inspection report and prepare approval note

Status:
● COMPLETED

Duration:
14.8 seconds

Model:
local-general

──────────────────────────────────────────────────────────────

✓ 01 Input validated
      report.pdf

✓ 02 Task classified
      DOCUMENT_ANALYSIS

✓ 03 Model selected
      local-general

✓ 04 OCR executed
      PaddleOCR
      6 pages

✓ 05 Hybrid retrieval
      Qdrant
      8 candidates → 3 final chunks

✓ 06 Evidence validated
      Maintenance_SOP.pdf
      pages 17, 23

✓ 07 Artifact generated
      approval_note.docx

✓ 08 Sovereignty check
      External calls: 0

──────────────────────────────────────────────────────────────

[View Sources] [View Artifact] [Network Events]
```

The existing backend event contract already supports task
classification, model selection, tools, evidence, artifact creation, and
completion. fileciteturn5file19

------------------------------------------------------------------------

# 13. Execution Detail Drawer

Clicking a step opens detailed metadata.

Example:

``` text
HYBRID RAG

Tool:
qdrant_hybrid_search

Dense:
5 results

BM25:
5 results

RRF:
8 candidates

Reranker:
3 final chunks

Sources:
• Maintenance_SOP.pdf p.17
• Maintenance_SOP.pdf p.23
• Safety_Manual.pdf p.42

Duration:
1.2s
```

------------------------------------------------------------------------

# 14. Model Registry

``` text
┌──────────────────────────────────────────────────────────────────┐
│ MODEL REGISTRY                                     [+ Register]  │
├──────────────────────────────────────────────────────────────────┤
│ GENERAL LLM                                                     │
│ local-general                                                   │
│ Status: ● READY                                                 │
│ Capabilities: reasoning • tools • summarization                  │
│                                                                  │
│ CODING LLM                                                      │
│ Qwen2.5-Coder-3B-Instruct                                       │
│ Status: ● READY                                                 │
│ Capabilities: code • debugging • analysis                       │
│                                                                  │
│ VISION MODEL                                                    │
│ local-vlm                                                       │
│ Status: ● READY / STANDBY                                       │
│ Capabilities: image • scanned document • drawing                │
└──────────────────────────────────────────────────────────────────┘
```

Each model card can show:

``` text
VRAM estimate
Context length
Capabilities
Current state
Requests
Average latency
```

The UI shows routing information but does not perform authoritative
routing.

------------------------------------------------------------------------

# 15. Artifacts

Artifacts are first-class objects.

``` text
┌──────────────────────────────────────────────────────────────────┐
│ ARTIFACTS                                                        │
├──────────────────────────────────────────────────────────────────┤
│ Name                     Type   Created       Execution           │
├──────────────────────────────────────────────────────────────────┤
│ approval_note.docx       DOCX   2 min ago     EX-1042             │
│ downtime_analysis.py     PY     8 min ago     EX-1039             │
│ downtime_analysis.xlsx   XLSX   8 min ago     EX-1039             │
│ board_presentation.pptx  PPTX   21 min ago    EX-1031             │
└──────────────────────────────────────────────────────────────────┘
```

Artifact detail:

``` text
approval_note.docx

Generated by:
local-general

Execution:
EX-1042

Sources:
Maintenance_SOP.pdf
Inspection_Report.pdf

[Preview] [Download]
```

The backend generates artifacts. The frontend handles:

-   Preview
-   Metadata
-   Download
-   Execution association
-   Source display

------------------------------------------------------------------------

# 16. Network Monitor

This is the visual proof of sovereignty.

``` text
┌──────────────────────────────────────────────────────────────────┐
│ NETWORK MONITOR                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│              ● AIR-GAPPED / LOCAL                               │
│                                                                  │
│ External AI Calls                         0                     │
│ Cloud API Calls                           0                     │
│ Blocked Connections                       3                     │
│ Local Connections                        184                    │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│ LIVE EVENTS                                                       │
├──────────────────────┬──────────────┬──────────┬─────────────────┤
│ Time                 │ Destination  │ Action   │ Process         │
├──────────────────────┼──────────────┼──────────┼─────────────────┤
│ 15:41:02             │ example:443  │ BLOCKED  │ backend         │
│ 15:41:10             │ qdrant:6333  │ LOCAL    │ backend         │
│ 15:41:11             │ postgres:5432│ LOCAL    │ backend         │
└──────────────────────┴──────────────┴──────────┴─────────────────┘
```

Optional topology:

``` text
              SOVEREIGN BOUNDARY
       ┌─────────────────────────────┐
       │ vLLM │ Qdrant │ PG │ Piston │
       └─────────────────────────────┘
                     X
                INTERNET
                  BLOCKED
```

### Important rule

The frontend must never fake sovereignty values.

It only renders backend/infrastructure telemetry.

The backend/infrastructure layer is responsible for enforcement and
measurement.

------------------------------------------------------------------------

# 17. System Health

``` text
┌──────────────────────────────────────────────────────────────────┐
│ SYSTEM HEALTH                                                     │
├──────────────────────────────────────────────────────────────────┤
│ Backend API             ● HEALTHY                                │
│ PostgreSQL              ● HEALTHY                                │
│ Qdrant                  ● HEALTHY                                │
│ vLLM General            ● HEALTHY                                │
│ vLLM Coder              ● HEALTHY                                │
│ vLLM Vision             ● STANDBY                                │
│ Piston                  ● HEALTHY                                │
│ OCR                     ● AVAILABLE                              │
├──────────────────────────────────────────────────────────────────┤
│ HARDWARE                                                         │
│ GPU                     RTX 4050                                 │
│ VRAM                    4.8 / 6 GB                               │
│ Temperature             61°C                                     │
└──────────────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 18. Frontend Technology

``` text
React
TypeScript
Tailwind CSS
shadcn/ui
```

The frontend is component-driven.

------------------------------------------------------------------------

# 19. Frontend Folder Structure

``` text
frontend/
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   └── providers.tsx
│   │
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── Workbench.tsx
│   │   ├── KnowledgeBase.tsx
│   │   ├── Execution.tsx
│   │   ├── Models.tsx
│   │   ├── Artifacts.tsx
│   │   ├── NetworkMonitor.tsx
│   │   └── System.tsx
│   │
│   ├── components/
│   │   ├── layout/
│   │   ├── chat/
│   │   ├── upload/
│   │   ├── knowledge/
│   │   ├── execution/
│   │   ├── models/
│   │   ├── artifacts/
│   │   ├── network/
│   │   └── system/
│   │
│   ├── api/
│   │   ├── client.ts
│   │   ├── chat.ts
│   │   ├── documents.ts
│   │   ├── models.ts
│   │   ├── executions.ts
│   │   ├── artifacts.ts
│   │   └── system.ts
│   │
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useExecution.ts
│   │   ├── useModels.ts
│   │   ├── useDocuments.ts
│   │   ├── useArtifacts.ts
│   │   └── useNetworkMonitor.ts
│   │
│   ├── stores/
│   │   ├── workbenchStore.ts
│   │   └── uiStore.ts
│   │
│   ├── types/
│   │   ├── api.ts
│   │   ├── agent.ts
│   │   ├── document.ts
│   │   ├── model.ts
│   │   ├── artifact.ts
│   │   └── network.ts
│   │
│   └── lib/
│       ├── utils.ts
│       └── formatting.ts
│
├── package.json
└── README.md
```

------------------------------------------------------------------------

# 20. React Component Architecture

``` text
<App>
 ├── <AppShell>
 │    ├── <Sidebar />
 │    ├── <Topbar />
 │    └── <SovereigntyBadge />
 │
 ├── <DashboardPage>
 │    ├── <SovereigntyCard />
 │    ├── <GpuCard />
 │    ├── <ServiceHealthGrid />
 │    ├── <RecentExecutions />
 │    └── <NetworkSummary />
 │
 ├── <WorkbenchPage>
 │    ├── <ChatPanel />
 │    │    ├── <ConversationList />
 │    │    ├── <MessageList />
 │    │    ├── <Message />
 │    │    ├── <SourceCitations />
 │    │    └── <ArtifactCard />
 │    ├── <TaskContextPanel />
 │    ├── <ExecutionTrace />
 │    └── <Composer />
 │
 ├── <KnowledgeBasePage>
 │    ├── <DocumentUploader />
 │    ├── <DocumentTable />
 │    └── <KnowledgeSearch />
 │
 ├── <ExecutionPage>
 │    ├── <ExecutionHeader />
 │    ├── <ExecutionTimeline />
 │    ├── <EvidencePanel />
 │    └── <ArtifactPanel />
 │
 ├── <ModelsPage>
 │    └── <ModelCard />
 │
 ├── <ArtifactsPage>
 │    └── <ArtifactTable />
 │
 ├── <NetworkMonitorPage>
 │    ├── <NetworkSummary />
 │    └── <NetworkEventTable />
 │
 └── <SystemPage>
      ├── <ServiceHealthGrid />
      └── <HardwarePanel />
```

------------------------------------------------------------------------

# 21. Frontend ↔ Backend Architecture

The architecture is:

``` text
FRONTEND
React + TypeScript
        |
        | REST / SSE
        v
     FASTAPI
        |
        +--> LangGraph
        +--> Model Router
        +--> RAG
        +--> Tools
        +--> PostgreSQL
        +--> Qdrant
        +--> vLLM
        +--> Piston
        +--> Local Files
```

The backend architecture already defines FastAPI, LangGraph, model
routing, Qdrant, vLLM, Piston, PostgreSQL, local artifacts, and
streaming execution events. fileciteturn5file2

------------------------------------------------------------------------

# 22. Backend Responsibility Boundary

The frontend must NOT contain:

-   Model inference
-   RAG
-   OCR
-   Agent planning
-   Sandbox execution
-   Document parsing
-   Network enforcement
-   Security-critical validation

The backend owns those responsibilities.

The frontend owns:

-   User interaction
-   Rendering
-   Upload initiation
-   Streaming display
-   Execution visualization
-   Source display
-   Artifact presentation
-   System telemetry display

------------------------------------------------------------------------

# 23. API Base URL

Use one configurable base URL:

``` text
VITE_API_BASE_URL=http://localhost:8000
```

Docker/demo:

``` text
Browser
   ↓
Frontend
   ↓
FastAPI
```

The browser should not directly access internal Docker services.

------------------------------------------------------------------------

# 24. API Client

Create:

``` text
src/api/client.ts
```

Responsibilities:

-   Base URL
-   JSON requests
-   Multipart upload
-   Session/auth headers if introduced
-   Error normalization
-   Request IDs
-   Timeout handling

Expose typed methods:

``` text
api.chat()
api.runAgent()
api.uploadDocument()
api.ingestDocument()
api.searchKnowledge()
api.getModels()
api.routeModel()
api.getExecution()
api.getArtifact()
api.getSystemStatus()
api.getNetworkMonitor()
```

------------------------------------------------------------------------

# 25. API Map

``` text
FRONTEND
│
├── POST /api/chat
│     └── Chat + streaming
│
├── POST /api/agent/run
│     └── Full agent execution
│
├── POST /api/documents/upload
│     └── Upload
│
├── POST /api/documents/ingest
│     └── Ingestion
│
├── GET /api/documents
│     └── Knowledge Base
│
├── POST /api/rag/search
│     └── Retrieval testing
│
├── GET /api/models
│     └── Model Registry
│
├── POST /api/models/route
│     └── Routing inspection
│
├── POST /api/sandbox/execute
│     └── Controlled execution
│
├── GET /api/executions/{id}
│     └── Execution details
│
├── GET /api/artifacts/{id}
│     └── Artifact retrieval
│
├── GET /api/system/status
│     └── Health
│
└── GET /api/network/monitor
      └── Sovereignty telemetry
```

The frontend should only use endpoints that actually exist in the
backend implementation; this map is the frontend contract target.

------------------------------------------------------------------------

# 26. Chat / Agent Run

Primary endpoint:

``` text
POST /api/agent/run
```

Request:

``` json
{
  "message": "Analyze the inspection report and prepare an approval note",
  "attachments": ["doc_123"],
  "mode": "sovereign"
}
```

The backend streams execution events.

The existing backend blueprint defines this contract and event sequence.
fileciteturn5file19

------------------------------------------------------------------------

# 27. Streaming Architecture

Preferred transport:

``` text
Server-Sent Events
```

Flow:

``` text
USER
  ↓
POST /api/agent/run
  ↓
FASTAPI
  ↓
LANGGRAPH
  ↓
task_classified
  ↓
model_selected
  ↓
tool_started
  ↓
evidence
  ↓
artifact_created
  ↓
completed
  ↓
FRONTEND
```

The UI updates in real time.

------------------------------------------------------------------------

# 28. Event Contract

Support:

``` json
{
  "type": "task_classified",
  "task": "DOCUMENT_ANALYSIS"
}
```

``` json
{
  "type": "model_selected",
  "model": "local-general"
}
```

``` json
{
  "type": "tool_started",
  "tool": "ocr"
}
```

``` json
{
  "type": "tool_started",
  "tool": "hybrid_rag"
}
```

``` json
{
  "type": "evidence",
  "source": "maintenance_sop.pdf",
  "page": 17
}
```

``` json
{
  "type": "artifact_created",
  "artifact_id": "art_123"
}
```

``` json
{
  "type": "completed",
  "external_calls": 0
}
```

Recommended additional UI events:

``` text
message_delta
tool_completed
step_complete
network_event
error
```

------------------------------------------------------------------------

# 29. Event → UI Mapping

  Backend event        Frontend behavior
  -------------------- -------------------------
  `task_classified`    Add classification step
  `model_selected`     Show selected model
  `tool_started`       Add running step
  `tool_completed`     Mark successful
  `step_complete`      Record timing/result
  `evidence`           Add source citation
  `message_delta`      Stream response text
  `artifact_created`   Show artifact card
  `network_event`      Update network monitor
  `error`              Show structured error
  `completed`          Mark execution complete

------------------------------------------------------------------------

# 30. Document Upload

Flow:

``` text
User selects file
      ↓
POST /api/documents/upload
      ↓
FastAPI validation
      ↓
Document registered
      ↓
document_id
      ↓
Frontend status
```

Example:

``` json
{
  "document_id": "doc_123",
  "filename": "inspection_report.pdf",
  "status": "uploaded"
}
```

Then:

``` text
POST /api/documents/ingest
```

Backend:

``` text
Parse
↓
OCR
↓
Chunk
↓
Embedding
↓
BM25
↓
Qdrant
↓
Metadata
```

------------------------------------------------------------------------

# 31. Knowledge Base API

``` text
GET /api/documents
```

Displays:

``` text
Document
Type
Status
Pages
Chunks
Created
Checksum
```

Search:

``` text
POST /api/rag/search
```

Example:

``` json
{
  "query": "pump vibration maintenance procedure",
  "top_k": 5
}
```

Display:

``` text
Dense
BM25
RRF
Reranker
Sources
```

------------------------------------------------------------------------

# 32. Model Registry API

``` text
GET /api/models
```

Displays:

``` text
Model
Status
Capabilities
Context
Resource notes
```

Optional routing inspection:

``` text
POST /api/models/route
```

Example:

``` text
Request:
Analyze CSV

Selected:
Qwen2.5-Coder-3B-Instruct

Reason:
DATA_ANALYSIS + CODE_EXECUTION
```

The frontend displays the routing decision; the backend owns it.

------------------------------------------------------------------------

# 33. Execution API

``` text
GET /api/executions/{id}
```

Expected shape:

``` text
Execution
├── status
├── task_type
├── selected_model
├── steps[]
├── observations[]
├── artifacts[]
└── errors[]
```

The frontend renders the timeline.

------------------------------------------------------------------------

# 34. Artifact API

``` text
GET /api/artifacts/{id}
```

Artifacts can include:

``` text
approval_note.docx
analysis.xlsx
analysis.py
presentation.pptx
```

Frontend responsibilities:

``` text
Preview
Metadata
Download
Execution association
Source display
```

Backend responsibilities:

``` text
Generate
Store
Validate
Audit
```

------------------------------------------------------------------------

# 35. Network Monitor API

Preferred:

``` text
GET /api/network/monitor
```

Transport:

``` text
SSE
```

Example event:

``` json
{
  "timestamp": "2026-08-26T15:41:02",
  "destination": "example.com:443",
  "action": "blocked",
  "process": "backend"
}
```

Frontend displays:

``` text
External AI Calls: 0
Blocked: 3
Local: 184
```

The frontend does not calculate sovereignty independently.

------------------------------------------------------------------------

# 36. System Status API

``` text
GET /api/system/status
```

Possible response:

``` json
{
  "backend": "healthy",
  "postgres": "healthy",
  "qdrant": "healthy",
  "vllm_general": "healthy",
  "vllm_coder": "healthy",
  "vllm_vision": "standby",
  "piston": "healthy"
}
```

Frontend maps this into service cards.

------------------------------------------------------------------------

# 37. Frontend State

Keep frontend state lightweight.

## Workbench

``` text
conversationId
messages
attachments
activeExecutionId
streaming
selectedTask
selectedSources
selectedArtifact
```

## System

``` text
serviceHealth
gpuUsage
modelStatus
sovereigntyStatus
networkCounters
```

## UI

``` text
sidebarOpen
activePanel
traceExpanded
sourceDrawerOpen
artifactDrawerOpen
```

Do not duplicate backend state unnecessarily.

------------------------------------------------------------------------

# 38. Security Rules

The frontend must:

1.  Never expose model provider secrets.
2.  Never expose database credentials.
3.  Never directly connect to PostgreSQL.
4.  Never directly connect to Qdrant.
5.  Never directly connect to vLLM.
6.  Never directly execute generated code.
7.  Never treat frontend task classification as authoritative.
8.  Never trust frontend sovereignty counters.
9.  Safely render backend-generated content.
10. Use backend-generated artifact IDs/URLs.
11. Never bypass FastAPI security boundaries.
12. Never assume a network event is trustworthy without backend
    validation.

The backend remains the security authority.

------------------------------------------------------------------------

# 39. Authentication

For v1:

``` text
Keep authentication lightweight.
```

Architecture should reserve:

``` text
AuthProvider
UserSession
ProtectedRoute
```

Enterprise SSO/RBAC should not delay the core PS demonstration.

------------------------------------------------------------------------

# 40. Error UX

Bad:

``` text
500 Internal Server Error
```

Better:

``` text
Unable to execute the requested task.

Reason:
The coding model is currently unavailable.

Suggested action:
Retry the task or select another available model.

Execution:
EX-1042
```

Security error:

``` text
Execution blocked.

Reason:
Generated code attempted a restricted operation.

The code was not executed outside the sandbox.
```

------------------------------------------------------------------------

# 41. Loading UX

Avoid generic spinners.

Use:

``` text
Working...

✓ Reading input
✓ Classifying task
→ Selecting model
○ Retrieving knowledge
○ Executing tools
○ Validating result
○ Generating artifact
```

This makes the agent feel active without exposing hidden reasoning.

------------------------------------------------------------------------

# 42. Empty States

## Knowledge Base

``` text
Your local knowledge base is empty.

Upload SOPs, manuals, reports or correspondence
to create your organization's private AI memory.

[Upload Documents]
```

## Artifacts

``` text
No artifacts yet.

Generated Word, Excel, PowerPoint and code files
will appear here.
```

## Executions

``` text
No executions yet.

Start a task from the AI Workbench.
```

------------------------------------------------------------------------

# 43. Demo Experience

The frontend must be optimized for the three core PS demonstrations,
with correspondence search available as an additional capability.

The backend's original architecture identifies three repeatable golden
demos, while the expanded plan adds correspondence RAG and a network
monitor. fileciteturn5file3

## Demo 1 --- Inspection → Approval Note

``` text
Upload inspection_report.pdf
        ↓
Task classification
        ↓
General model selected
        ↓
OCR
        ↓
Hybrid RAG
        ↓
SOP evidence
        ↓
Analysis
        ↓
approval_note.docx
        ↓
External Calls: 0
```

Visible trace:

``` text
✓ Task classified
✓ General model selected
✓ OCR completed
✓ Hybrid RAG completed
✓ SOP evidence found
✓ Analysis completed
✓ approval_note.docx generated
✓ External calls: 0
```

------------------------------------------------------------------------

## Demo 2 --- Coding / Data Analysis

``` text
Upload machine_downtime.csv
        ↓
Task classification
        ↓
Coder model selected
        ↓
Python generated
        ↓
Sandbox validation
        ↓
Piston execution
        ↓
Result verified
        ↓
analysis.py
analysis.xlsx
        ↓
External Calls: 0
```

------------------------------------------------------------------------

## Demo 3 --- Multimodal

``` text
Upload pump_assembly.png
        ↓
VLM selected
        ↓
Visual analysis
        ↓
Optional SOP retrieval
        ↓
Structured result
        ↓
External Calls: 0
```

------------------------------------------------------------------------

## Optional Demo 4 --- Correspondence

``` text
Upload email archive
        ↓
Correspondence ingestion
        ↓
Hybrid RAG
        ↓
Evidence
        ↓
Synthesis
        ↓
Sources shown
```

This is useful because the expanded backend plan explicitly adds
correspondence ingestion/RAG. fileciteturn5file13

------------------------------------------------------------------------

# 44. Demo Mode Rules

During judging, prioritize:

``` text
1. AI Workbench
2. Execution Trace
3. Artifact
4. Network Monitor
```

Do not spend valuable demo time navigating deep technical pages.

The UI should make the critical proof visible in the main workbench.

------------------------------------------------------------------------

# 45. Responsive Design

Primary:

``` text
Desktop 1440px+
```

Secondary:

``` text
Laptop 1280px
```

Minimum practical:

``` text
1024px
```

Behavior:

``` text
>1400px
Full multi-panel layout

1024–1400px
Main content + trace drawer

768–1024px
Single column + bottom trace sheet

<768px
Mobile fallback
```

Desktop remains the priority because this is an enterprise workstation.

------------------------------------------------------------------------

# 46. Accessibility

Support:

-   Keyboard navigation
-   Visible focus states
-   Proper labels
-   Accessible dialogs
-   Readable contrast
-   Screen-reader status announcements
-   Accessible async notifications
-   ARIA labels for icon-only buttons

Target contrast:

``` text
≥ 4.5:1
```

------------------------------------------------------------------------

# 47. Component Library

## Buttons

``` text
Primary
Secondary
Danger
Ghost
Icon
```

## Status badges

``` text
✓ Success
● Online
◐ Standby
○ Offline
⚠ Warning
⛔ Blocked
● LOCAL ONLY
```

## Cards

``` text
Background: #161B22
Border: #30363D
Radius: 8px
Padding: 16px
```

## Execution step

``` text
┌─────────────────────────────────────────────────────────┐
│ ✓ Step 4: HYBRID_RAG                         1.2s       │
│   Tool: Qdrant + BM25                                  │
│   Chunks: 4                                             │
│   Evidence: SOP.pdf p.17, p.23                         │
└─────────────────────────────────────────────────────────┘
```

States:

``` text
pending
running
success
failed
```

------------------------------------------------------------------------

# 48. Final Frontend Development Order

The frontend should be developed alongside backend phases.

## Phase 1 --- Shell

Build:

``` text
AppShell
Sidebar
Topbar
SovereigntyBadge
Dashboard
```

Connect:

``` text
GET /api/system/status
```

Exit:

> UI can display backend/service health.

------------------------------------------------------------------------

## Phase 2 --- Workbench

Build:

``` text
Chat
Composer
File upload
Streaming
```

Connect:

``` text
POST /api/chat
POST /api/agent/run
```

Exit:

> User can submit a task and receive a streamed response.

------------------------------------------------------------------------

## Phase 3 --- Execution Trace

Build:

``` text
ExecutionTimeline
StepCard
EvidencePanel
ArtifactCard
```

Exit:

> User can visibly follow agent execution.

------------------------------------------------------------------------

## Phase 4 --- Knowledge Base

Build:

``` text
DocumentTable
Upload
IngestionStatus
KnowledgeSearch
SourceViewer
```

Connect:

``` text
/documents
/documents/upload
/documents/ingest
/rag/search
```

Exit:

> User can upload and search local knowledge.

------------------------------------------------------------------------

## Phase 5 --- Model Registry

Build:

``` text
ModelCard
CapabilityBadges
ModelHealth
RoutingPreview
```

Connect:

``` text
/models
/models/route
```

Exit:

> User can see available local models and selected routing.

------------------------------------------------------------------------

## Phase 6 --- Artifacts

Build:

``` text
ArtifactTable
ArtifactPreview
DownloadButton
```

Exit:

> DOCX/XLSX/PPTX/code artifacts are accessible.

------------------------------------------------------------------------

## Phase 7 --- Network Monitor

Build:

``` text
NetworkSummary
NetworkEventTable
SovereigntyBadge
```

Connect:

``` text
/network/monitor
```

Exit:

> Judge can visibly inspect sovereignty telemetry.

------------------------------------------------------------------------

## Phase 8 --- Polish

Add:

-   Empty states
-   Error states
-   Loading states
-   Keyboard shortcuts
-   Responsive behavior
-   Demo mode
-   Visual consistency
-   Performance optimization

------------------------------------------------------------------------

# 49. Frontend Build Checklist

## Application Shell

-   [ ] React + TypeScript
-   [ ] Tailwind CSS
-   [ ] shadcn/ui
-   [ ] Sidebar
-   [ ] Global header
-   [ ] Sovereignty badge
-   [ ] System status

## AI Workbench

-   [ ] Chat
-   [ ] Streaming
-   [ ] File attachments
-   [ ] Drag-and-drop
-   [ ] Task context
-   [ ] Source citations
-   [ ] Artifact cards
-   [ ] Execution trace

## Knowledge Base

-   [ ] Document upload
-   [ ] Document table
-   [ ] Ingestion status
-   [ ] Metadata viewer
-   [ ] Search
-   [ ] Retrieval debug view
-   [ ] Correspondence support

## Agent Observability

-   [ ] Task classification
-   [ ] Model selection
-   [ ] Tool execution
-   [ ] Evidence
-   [ ] Artifact generation
-   [ ] Duration
-   [ ] Execution status

## Models

-   [ ] Registry
-   [ ] Capabilities
-   [ ] Health
-   [ ] Resource information
-   [ ] Routing explanation

## Artifacts

-   [ ] DOCX
-   [ ] XLSX
-   [ ] PPTX
-   [ ] Python/code
-   [ ] Preview
-   [ ] Download
-   [ ] Execution association

## Sovereignty

-   [ ] Local mode indicator
-   [ ] External call counter
-   [ ] Network monitor
-   [ ] Blocked event display
-   [ ] Local service status

## System

-   [ ] Backend health
-   [ ] PostgreSQL
-   [ ] Qdrant
-   [ ] vLLM
-   [ ] Piston
-   [ ] OCR
-   [ ] GPU information

## UX

-   [ ] Loading states
-   [ ] Error states
-   [ ] Empty states
-   [ ] Keyboard navigation
-   [ ] Responsive desktop layout
-   [ ] Demo mode
-   [ ] Professional visual language

------------------------------------------------------------------------

# 50. Final Frontend Principle

The final product should feel like:

> **Claude/Codex-style interaction + enterprise document workbench +
> engineering agent console + visible sovereign infrastructure.**

The frontend should make the backend understandable without exposing its
internal reasoning.

The ideal judge experience is:

``` text
OPEN APPLICATION
      ↓
SEE LOCAL / AIR-GAPPED
      ↓
UPLOAD CONFIDENTIAL DOCUMENT
      ↓
ASK A REAL WORK TASK
      ↓
WATCH TASK CLASSIFICATION
      ↓
WATCH MODEL ROUTING
      ↓
WATCH OCR / RAG / TOOLS
      ↓
SEE EVIDENCE
      ↓
SEE VERIFIED RESULT
      ↓
DOWNLOAD REAL ARTIFACT
      ↓
OPEN NETWORK MONITOR
      ↓
SEE EXTERNAL CALLS: 0
```

That is the frontend's core job:

> **Make the sovereign agent visible, understandable, auditable, and
> impressive.**
