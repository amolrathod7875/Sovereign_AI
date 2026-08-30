/**
 * Centralized Sovereign AI frontend API client.
 *
 * This is the SINGLE place the browser talks to the local FastAPI backend. Every
 * page/component imports from here — there is no scattered `fetch`/`axios`/`XHR`
 * elsewhere. The base URL is environment-driven (VITE_API_BASE_URL, default `/api`
 * which Vite proxies to http://localhost:8000 — see vite.config.ts), so no
 * production IP is hard-coded and the browser only ever reaches the local backend.
 *
 * All request/response shapes mirror the backend Pydantic models in
 * `backend/app/schemas/api.py` and `backend/app/api/*` (see ./types.ts).
 */
import axios, { AxiosError, type AxiosInstance } from 'axios'
import type {
  HealthResponse,
  SystemStatus,
  ModelInfo,
  RoutingRequest,
  RoutingDecision,
  AgentRunRequest,
  AgentRunResponse,
  CoderRunResponse,
  VisionAnalyzeResponse,
  SupportedFormats,
  DocumentUploadResponse,
  DocumentResponse,
  RagSearchResponse,
  ArtifactInfo,
  NetworkEvent,
  RunSummary,
} from './types'

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  (typeof globalThis !== 'undefined' && (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.VITE_API_BASE_URL) ||
  '/api'

const CONTROL_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT_MS || 30000)
const INFERENCE_TIMEOUT = Number(import.meta.env.VITE_INFERENCE_TIMEOUT_MS || 2_400_000)

/** Typed error: carries the HTTP status and the backend's human-facing detail. */
export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function friendlyDetail(status: number, data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'detail' in (data as Record<string, unknown>)) {
    const d = (data as Record<string, unknown>).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((e) => (e && typeof e === 'object' && 'msg' in e ? String((e as any).msg) : String(e))).join('; ')
  }
  if (status === 0) return 'Cannot reach the local backend. Is the FastAPI server running on the configured origin?'
  return fallback
}

function makeClient(timeout: number): AxiosInstance {
  const client = axios.create({
    baseURL: BASE_URL,
    timeout,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
  })
  client.interceptors.response.use(
    (resp) => resp,
    (err: AxiosError) => {
      const status = err.response?.status ?? 0
      const detail = friendlyDetail(status, err.response?.data, err.message)
      return Promise.reject(new ApiError(status, detail))
    },
  )
  return client
}

// Long-running inference (agent/coder/vision) and short control-plane calls use
// different timeouts so a 10-minute CPU coding run is not aborted, while a status
// probe fails fast.
const api = makeClient(CONTROL_TIMEOUT)
const inference = makeClient(INFERENCE_TIMEOUT)

// ---------------------------------------------------------------------------
// Health / System
// ---------------------------------------------------------------------------
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/system/health')
  return data
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>('/system/status')
  return data
}

// ---------------------------------------------------------------------------
// Models / Routing
// ---------------------------------------------------------------------------
export async function listModels(): Promise<ModelInfo[]> {
  const { data } = await api.get<ModelInfo[]>('/models')
  return data
}

export async function routeTask(req: Partial<RoutingRequest>): Promise<RoutingDecision> {
  const { data } = await api.post<RoutingDecision>('/models/route', req)
  return data
}

// ---------------------------------------------------------------------------
// Agent (maintenance / knowledge / multimodal)
// ---------------------------------------------------------------------------
export async function runAgent(req: AgentRunRequest): Promise<AgentRunResponse> {
  const { data } = await inference.post<AgentRunResponse>('/agent/run', req)
  return data
}

export async function listAgentRuns(limit = 50): Promise<RunSummary[]> {
  const { data } = await api.get<RunSummary[]>('/agent/runs', { params: { limit } })
  return data
}

// ---------------------------------------------------------------------------
// Coder
// ---------------------------------------------------------------------------
export async function runCoder(task: string): Promise<CoderRunResponse> {
  const { data } = await inference.post<CoderRunResponse>('/coder/run', { task })
  return data
}

export async function listCoderRuns(limit = 50): Promise<RunSummary[]> {
  const { data } = await api.get<RunSummary[]>('/coder/runs', { params: { limit } })
  return data
}

// ---------------------------------------------------------------------------
// Vision
// ---------------------------------------------------------------------------
export async function analyzeVision(req: {
  file_path: string
  analysis_type?: string
  prompt?: string | null
}): Promise<VisionAnalyzeResponse> {
  const { data } = await inference.post<VisionAnalyzeResponse>('/vision/analyze', {
    file_path: req.file_path,
    analysis_type: req.analysis_type ?? 'general',
    prompt: req.prompt ?? null,
  })
  return data
}

// ---------------------------------------------------------------------------
// Documents / Upload / Ingestion
// ---------------------------------------------------------------------------
export async function getSupportedFormats(): Promise<SupportedFormats> {
  const { data } = await api.get<SupportedFormats>('/documents/formats')
  return data
}

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<DocumentUploadResponse>('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: CONTROL_TIMEOUT,
  })
  return data
}

export async function ingestDocument(documentId: string): Promise<unknown> {
  const { data } = await inference.post<unknown>('/documents/ingest', null, {
    params: { document_id: documentId },
  })
  return data
}

export async function listDocuments(): Promise<DocumentResponse[]> {
  const { data } = await api.get<DocumentResponse[]>('/documents')
  return data
}

// ---------------------------------------------------------------------------
// RAG
// ---------------------------------------------------------------------------
export async function searchRag(req: {
  query: string
  top_k?: number
  asset_tag?: string | null
  document_type?: string | null
}): Promise<RagSearchResponse> {
  const { data } = await inference.post<RagSearchResponse>('/rag/search', {
    query: req.query,
    top_k: req.top_k ?? 8,
    asset_tag: req.asset_tag ?? null,
    document_type: req.document_type ?? null,
  })
  return data
}

// ---------------------------------------------------------------------------
// Artifacts (read-only — generation happens in the backend)
// ---------------------------------------------------------------------------
export async function listArtifacts(opts?: {
  kind?: string
  run_id?: string
}): Promise<ArtifactInfo[]> {
  const { data } = await api.get<ArtifactInfo[]>('/artifacts', {
    params: { kind: opts?.kind, run_id: opts?.run_id, limit: 200 },
  })
  return data
}

export function artifactDownloadUrl(artifactId: string): string {
  return `${BASE_URL}/artifacts/${artifactId}/download`
}

// ---------------------------------------------------------------------------
// Network
// ---------------------------------------------------------------------------
export async function getNetworkEvents(limit = 100): Promise<NetworkEvent[]> {
  const { data } = await api.get<NetworkEvent[]>('/network/events', { params: { limit } })
  return data
}

export const apiClient = {
  getHealth,
  getSystemStatus,
  listModels,
  routeTask,
  runAgent,
  listAgentRuns,
  runCoder,
  listCoderRuns,
  analyzeVision,
  getSupportedFormats,
  uploadDocument,
  ingestDocument,
  listDocuments,
  searchRag,
  listArtifacts,
  artifactDownloadUrl,
  getNetworkEvents,
}

export default apiClient
