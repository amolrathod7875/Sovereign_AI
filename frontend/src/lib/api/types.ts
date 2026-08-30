/**
 * TypeScript mirrors of the backend Pydantic schemas.
 *
 * These are *read-only projections* of `backend/app/schemas/api.py` and the
 * request/response models declared inline in `backend/app/api/*.py`. They exist so
 * the UI is type-checked against the real contract; they intentionally do not
 * re-implement or extend any backend logic.
 *
 * Source of truth per type is noted in the comment above it.
 */

/** backend/app/api/system.py :: health_check */
export interface HealthResponse {
  status: string
  sovereign_mode: boolean
  uptime_seconds: number
}

/** backend/app/schemas/api.py :: ComponentStatus */
export type ComponentState = 'ONLINE' | 'OFFLINE' | 'UNAVAILABLE' | 'NOT CONFIGURED'

export interface ComponentStatus {
  id: string
  name: string
  status: ComponentState | string
  detail: string
  endpoint: string | null
  local: boolean
}

/** backend/app/schemas/api.py :: SystemStatus */
export interface GpuInfo {
  name: string | null
  memory_used_gb: number | null
  memory_total_gb: number | null
}

export interface SystemStatus {
  sovereign: boolean
  gpu: GpuInfo | null
  services: Record<string, { status: string; name?: string; detail?: string }>
  components: ComponentStatus[]
  uptime_seconds: number
  external_api_calls: number
  blocked_connections: number
}

/** backend/app/schemas/api.py :: ModelInfo */
export interface ModelInfo {
  id: string
  name: string
  endpoint: string
  capabilities: string[]
  context_length: number
  status: string
  vram_gb: number | null
  local: boolean
  modalities: string[]
}

/** backend/app/schemas/api.py :: RoutingRequest */
export interface RoutingRequest {
  task: string
  task_type?: string | null
  modality?: string | null
  has_image?: boolean
  image_path?: string | null
  requires_code?: boolean | null
  requires_vision?: boolean | null
  requires_rag?: boolean | null
  requires_tools?: boolean | null
  complexity?: string | null
  asset_tag?: string | null
  local_only?: boolean
}

/** backend/app/schemas/api.py :: RoutingDecision */
export interface RoutingDecision {
  task_type: string
  modality: string
  selected_model: string
  models_required: string[]
  requires_rag: boolean
  requires_tools: boolean
  confidence: number
  reason: string
  capabilities: string[]
  local_only: boolean
  all_local: boolean
  external_calls: number
}

/** backend/app/api/agent.py :: AgentRunRequest */
export interface AgentRunRequest {
  task: string
  asset_tag?: string
  image_path?: string | null
  analysis_type?: string
}

/** One retrieved evidence item as returned by agent.run.run_agent_task */
export interface AgentEvidence {
  claim: string | null
  source: string | null
  document_type: string | null
  confidence: number | null
}

/** agent/tools/vision.py :: structured vision result */
export interface VisionEvidence {
  file?: string
  analysis_type?: string
  description?: string
  findings?: string[]
  entities?: Array<{ type: string; name: string }>
  uncertain_items?: string[]
  confidence?: number
  model?: string
  data_origin?: string
  source_file?: string
  execution_time_s?: number
  pages?: Array<Record<string, unknown>>
  structured?: Record<string, unknown>
}

/** agent/utils.py :: trace_entry */
export interface TraceEntry {
  timestamp: string
  node: string
  action: string
  tool: string | null
  duration_ms: number
  status: string
  [key: string]: unknown
}

/** backend/app/api/agent.py :: AgentRunResponse */
export interface AgentRunResponse {
  run_id: string
  status: string
  decision: string | null
  reasoning_summary: string | null
  approval_required: boolean
  required_actions: string[]
  supporting_evidence: string[]
  findings: unknown[]
  artifacts: string[]
  evidence: AgentEvidence[]
  vision_evidence: VisionEvidence[]
  vision_tags: string[]
  calculations_summary: Record<string, unknown>
  verification: Record<string, unknown>
  trace: TraceEntry[]
  errors: unknown[]
  image_path: string | null
  analysis_type: string
  external_calls: number
  routing: RoutingDecision | null
}

/** backend/app/api/coder.py :: CoderRunResponse */
export interface CoderTestOutput {
  passed?: boolean
  exit_code?: number
  stdout?: string
  stderr?: string
  external_network_calls?: number
  [key: string]: unknown
}

export interface CoderRunResponse {
  run_id: string
  status: string
  files: string[]
  file_contents: Record<string, string>
  test_output: CoderTestOutput
  test_command: string
  iterations: number
  failure_analysis: string
  workspace: string
  execution_trace: TraceEntry[]
  errors: unknown[]
  external_calls: number
  routing: RoutingDecision | null
}

/** backend/app/api/vision.py :: VisionAnalyzeResponse */
export interface VisionAnalyzeResponse {
  status: string
  result: VisionEvidence
  model: string
  execution_time: number
  external_calls: number
  equipment_tags: string[]
}

/** backend/app/schemas/api.py :: DocumentUploadResponse */
export interface DocumentUploadResponse {
  document_id: string
  filename: string
  mime_type: string
  size: number
  checksum: string
  stored_path: string | null
  parse_supported: boolean
  vision_supported: boolean
}

/** backend/app/api/documents.py :: supported_formats */
export interface SupportedFormats {
  parse: string[]
  vision: string[]
  accept: string[]
  max_file_mb: number
  upload_dir: string
}

/** backend/app/schemas/api.py :: DocumentResponse */
export interface DocumentResponse {
  id: string
  filename: string
  mime_type: string
  size: number
  status: string
  doc_type: string
  pages: number | null
  chunks: number | null
  created_at: string
}

/** backend/app/api/rag.py :: RAGSearchResult / RAGSearchResponse */
export interface RagSearchResult {
  chunk_id: string
  text: string
  document_type: string
  source_file: string
  asset_tag: string
  data_origin: string
  section: string
  score: number
}

export interface RagSearchResponse {
  query: string
  retriever: string
  results: RagSearchResult[]
  count: number
}

/** backend/app/schemas/api.py :: ArtifactInfo */
export interface ArtifactInfo {
  artifact_id: string
  filename: string
  kind: string
  size: number
  mime_type: string
  modified_at: string
  run_id: string | null
}

/** backend/app/schemas/api.py :: NetworkEvent */
export interface NetworkEvent {
  id: string
  timestamp: string
  destination_host: string
  destination_port: number
  action: string
  execution_id: string | null
  process?: string
}

/** Network monitor connection states */
export type NetworkMonitorState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error'

/** backend/app/schemas/api.py :: ExecutionResponse */
export interface ExecutionStep {
  step_index: number
  action: string
  status: string
  model: string | null
  tool: string | null
  duration_ms: number | null
  metadata: Record<string, unknown> | null
}

export interface ExecutionResponse {
  id: string
  task_type: string
  status: string
  selected_model: string | null
  steps: ExecutionStep[]
  artifacts: string[]
  errors: string[]
  external_calls: number
  started_at: string
  completed_at: string | null
}

/** backend/app/api/agent.py :: list_runs / app/api/coder.py :: list_coder_runs */
export interface RunSummary {
  run_id: string
  status: string
  decision?: string | null
  approval_required?: boolean
  artifacts?: string[]
  files?: string[]
  external_calls: number
  selected_model: string | null
  task_type: string | null
}
