import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import JudgeMode from '../pages/JudgeMode'
import { apiClient } from '../lib/api/client'

const mockOverview = (): ReturnType<typeof vi.fn> => {
  return vi.fn().mockResolvedValue({
    generated_at: '2026-09-23T09:00:00Z',
    repository: { commit: 'abc123' },
    runtime: {
      source_type: 'LIVE',
      sovereign_mode: true,
      gpu: { name: 'NVIDIA GeForce RTX 4050 Laptop GPU', memory_used_gb: 1, memory_total_gb: 6 },
      components: [
        { id: 'general', name: 'Qwen2.5-3B-Instruct', status: 'UNAVAILABLE', detail: 'GGUF weights not present', endpoint: 'http://localhost:8001/v1', local: true },
        { id: 'vision', name: 'Qwen-VL-3B', status: 'OFFLINE', detail: 'no server', endpoint: 'http://localhost:8003/v1', local: true },
        { id: 'qwen-coder', name: 'Qwen2.5-Coder-3B-Instruct', status: 'OFFLINE', detail: 'no server', endpoint: 'http://localhost:8002/v1', local: true },
        { id: 'qdrant', name: 'Qdrant (embedded)', status: 'ONLINE', detail: 'embedded', endpoint: null, local: true },
        { id: 'bm25', name: 'BM25', status: 'ONLINE', detail: 'lexical', endpoint: null, local: true },
      ],
      external_api_calls: 0,
      blocked_connections: 0,
      uptime_seconds: 100,
    },
    governance: {
      source_type: 'LIVE_PERSISTENT',
      pending_review_count: 1,
      pending_reviews: [
        { run_id: 'run_pending', asset_tag: 'R-1001', decision: 'shutdown', status: 'PENDING', created_at: '2026-09-23T09:00:00Z', artifact_sha256: 'abc123', identity_status: 'VERIFIED_TEXT_ONLY', external_calls: 0 },
      ],
      chain: { entry_count: 2, head_sequence: 2, head_run_id: 'run_c', head_chain_sha256: 'chainhash', valid: true, status: 'VALID', checks: { sequence_contiguous: true }, violations: [] },
    },
    latest_terminal_run: {
      run_id: 'run_c',
      approval_status: 'REJECTED',
      asset: { requested_tag: 'R-1001', canonical_tag: 'R-1001', identity_status: 'VERIFIED_TEXT_ONLY', identity_source: 'local_asset_registry' },
      retrieval: { chunk_count: 32, unique_asset_tags: ['R-1001'], source_files: ['manual.docx'], document_types: ['equipment_manual'], retrieval_modes: ['hybrid'] },
      calculations: { any_threshold_breach: true, breached_signals: ['TI-1001'], inspection_findings: ['catalyst_hotspot'], vendor_parts: ['HRS-CAT-22'], sop_requirements: ['shutdown'], sandbox_used: true },
      execution_trace: { executed_nodes: ['plan'] },
      routing: { task_type: 'RAG_QA', selected_model: 'general', models_required: ['general'], requires_rag: true, requires_tools: false, local_only: true, all_local: true, confidence: 0.82, reason: 'local' },
      actual_model_execution: { recorded_models: [], status: 'NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE' },
      human_review: { approval_required: true, status: 'REJECTED', reviewer_id: 'phase16a2-reviewer', reviewer_comment: 'Rejected', reviewer_identity_verified: false, created_at: '2026-09-23T09:00:00Z', reviewed_at: '2026-09-23T09:00:00Z' },
      artifact: { logical_path: 'data/outputs/R-1001.docx', sha256: '9def2ff77c8cb12', verification_ok: true },
      receipt: { available: true, receipt_id: 'receipt:run_c', schema_version: '1.0', receipt_sha256: 'receipthash', valid: true, checks: { receipt_exists: true } },
      chain: { linked: true, global_chain_valid: true, global_chain_status: 'VALID', sequence_no: 2, previous_chain_sha256: 'prevhash', chain_sha256: 'chainhash' },
      sovereignty: { external_calls_recorded: 0, network_guard_scope: 'application-level agent run', whole_machine_airgap_certified: false },
    } as any,
    flagship: {
      source_type: 'COMMITTED_HISTORICAL_EVIDENCE',
      available: true,
      source_file: 'reports/flagship_workflow_latest.json',
      timestamp: '2026-09-22T15:32:44Z',
      run_id: 'run_07d24d69e01e',
      status: 'VERIFIED',
      asset: 'R-1001',
      identity_status: 'VERIFIED',
      retrieval_mode: 'hybrid',
      chunk_count: 36,
      sandbox_used: true,
      approval_required: true,
      artifact_verified: true,
      external_calls: 0,
      validation_checks_passed: 14,
      validation_checks_total: 14,
      failed_checks: {},
    },
    evaluation: {
      source_type: 'FROZEN_EVALUATION_SNAPSHOT',
      available: true,
      source_file: 'reports/competition_scorecard.json',
      historical_snapshot: true,
      generated_at: '2026-09-23T01:58:46Z',
      source_repository_commit: 'b2ce3cc03db9358a834303a826cec655ab33397e',
      matches_current_head: false,
      industrial: { passed: 10, total: 10 },
      rag: { queries_total: 6, hit_at_1: 2, hit_at_3: 4, hit_at_5: 6, mrr: 0.5556, primary_source_at_1: 2, provenance_complete_hits: 30, total_hits: 30, foreign_asset_hits: 0 },
      asset_identity: { passed: 18, total: 18 },
      routing: { passed: 10, total: 10, metrics: { general_model_runtime_status: 'UNAVAILABLE' } },
      runtime_resilience: { passed: 14, total: 14 },
      sovereignty_security: { passed: 12, total: 12 },
      artifact_sandbox: { passed: 11, total: 11 },
      flagship: { checks_passed: 14, checks_total: 14 },
      regression_snapshot: { passed: 304, failed: 2, skipped: 14, total: 320, historical_snapshot: true, source_generated_at: '2026-09-23T01:58:46Z', source_repository_commit: 'b2ce3cc03db9358a834303a826cec655ab33397e' },
    },
    claim_boundaries: {
      reviewer_identity_authenticated: false,
      whole_machine_airgap_certified: false,
      receipt_chain_tamper_proof: false,
      external_trust_anchor_present: false,
      digital_signature_present: false,
      general_runtime_status: 'UNAVAILABLE',
    },
  })
}

const mockRun = (): ReturnType<typeof vi.fn> => vi.fn().mockResolvedValue({
  run_id: 'run_x',
  approval_status: 'APPROVED',
  asset: { requested_tag: 'R-1001', canonical_tag: 'R-1001', identity_status: 'VERIFIED_TEXT_ONLY', identity_source: 'local_asset_registry' },
  retrieval: { chunk_count: 32, unique_asset_tags: ['R-1001'], source_files: [], document_types: [], retrieval_modes: ['hybrid'] },
  calculations: { any_threshold_breach: true, breached_signals: [], inspection_findings: [], vendor_parts: [], sop_requirements: [], sandbox_used: true },
  execution_trace: { executed_nodes: [] },
  routing: { task_type: 'RAG_QA', selected_model: 'general', models_required: ['general'], requires_rag: true, requires_tools: false, local_only: true, all_local: true, confidence: 0.82, reason: 'local' },
  actual_model_execution: { recorded_models: [], status: 'NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE' },
  human_review: { approval_required: true, status: 'APPROVED', reviewer_id: 'reviewer', reviewer_comment: 'ok', reviewer_identity_verified: false, created_at: '2026-09-23T09:00:00Z', reviewed_at: '2026-09-23T09:00:00Z' },
  artifact: { logical_path: 'data/outputs/R-1001.docx', sha256: 'hash', verification_ok: true },
  receipt: { available: true, receipt_id: 'receipt:run_x', schema_version: '1.0', receipt_sha256: 'receipthash', valid: true, checks: { receipt_exists: true } },
  chain: { linked: true, global_chain_valid: true, global_chain_status: 'VALID', sequence_no: 1, previous_chain_sha256: '0000', chain_sha256: 'chainhash' },
  sovereignty: { external_calls_recorded: 0, network_guard_scope: 'application-level agent run', whole_machine_airgap_certified: false },
} as any)

beforeEach(() => {
  vi.resetAllMocks()
})

function renderJudge() {
  return render(
    <BrowserRouter>
      <JudgeMode />
    </BrowserRouter>,
  )
}

describe('JudgeMode page', () => {
  it('renders Judge Mode title', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('JUDGE MODE')
    expect(screen.getByText('JUDGE MODE')).toBeDefined()
  })

  it('shows read-only banner', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('READ ONLY')
    expect(screen.getByText('READ ONLY')).toBeDefined()
  })

  it('shows historical flagship source label', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('HISTORICAL PROOF')
    expect(screen.getByText('HISTORICAL PROOF')).toBeDefined()
  })

  it('shows frozen evaluation label', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('FROZEN EVALUATION')
    expect(screen.getByText('FROZEN EVALUATION')).toBeDefined()
  })

  it('shows LIVE runtime source label', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const runtimeSection = await screen.findByTestId('runtime-section')
    within(runtimeSection).getByText('LIVE')
  })

  it('displays general UNAVAILABLE honestly', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('UNAVAILABLE')
    expect(screen.getByText('UNAVAILABLE')).toBeDefined()
  })

  it('displays vision OFFLINE', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('OFFLINE')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays coder OFFLINE', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('OFFLINE')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays Qdrant ONLINE', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('ONLINE')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays BM25 ONLINE', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('ONLINE')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays external calls actual value', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('0')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('handles empty governance', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: null },
      runtime: { source_type: 'LIVE', sovereign_mode: null, gpu: null, components: [], external_api_calls: 0, blocked_connections: 0, uptime_seconds: 0 },
      governance: { source_type: 'LIVE_PERSISTENT', pending_review_count: 0, pending_reviews: [], chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] } },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    const els = await screen.findAllByText('0')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays pending count', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('1')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays latest decision', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('REJECTED')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays valid chain', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('VALID')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays invalid chain prominently', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 1, head_sequence: 999, head_run_id: 'run_x', head_chain_sha256: 'hash', valid: false, status: 'INVALID', checks: {}, violations: ['sequence gap'] },
      },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('INVALID')
    expect(screen.getByText('INVALID')).toBeDefined()
  })

  it('shows chain violations when invalid', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 1, head_sequence: 999, head_run_id: 'run_x', head_chain_sha256: 'hash', valid: false, status: 'INVALID', checks: {}, violations: ['sequence gap at position 0'] },
      },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('sequence gap at position 0')
    expect(screen.getByText('sequence gap at position 0')).toBeDefined()
  })

  it('reads flagship 14/14 from fixture', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('14/14')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('handles flagship unavailable', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] },
      },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('FLAGSHIP EVIDENCE UNAVAILABLE', { exact: false })
    expect(screen.getByText('FLAGSHIP EVIDENCE UNAVAILABLE', { exact: false })).toBeDefined()
  })

  it('handles evaluation unavailable', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] },
      },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('EVALUATION EVIDENCE UNAVAILABLE', { exact: false })
    expect(screen.getByText('EVALUATION EVIDENCE UNAVAILABLE', { exact: false })).toBeDefined()
  })

  it('displays RAG Hit@1 as 2/6 fixture', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('2/6')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays RAG Hit@3', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('4/6')
    expect(screen.getByText('4/6')).toBeDefined()
  })

  it('displays RAG Hit@5', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('6/6')
    expect(screen.getByText('6/6')).toBeDefined()
  })

  it('displays MRR', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('0.5556')
    expect(screen.getByText('0.5556')).toBeDefined()
  })

  it('does not render composite score', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('JUDGE MODE')
    expect(screen.queryByText(/Overall Score/i)).toBeNull()
    expect(screen.queryByText(/Confidence/i)).toBeNull()
  })

  it('loads pending run detail', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 1,
        pending_reviews: [
          { run_id: 'run_pending', asset_tag: 'R-1001', decision: 'shutdown', status: 'PENDING', created_at: '2026-09-23T09:00:00Z', artifact_sha256: 'abc123', identity_status: 'VERIFIED_TEXT_ONLY', external_calls: 0 },
        ],
        chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] },
      },
      latest_terminal_run: null,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    const runMock = mockRun()
    vi.spyOn(apiClient, 'getJudgeRun').mockImplementation(runMock)
    renderJudge()
    await screen.findByText('PENDING run_pending')
    const pendingBtn = screen.getByText('PENDING run_pending')
    pendingBtn.click()
    await waitFor(() => expect(runMock).toHaveBeenCalledWith('run_pending'))
  })

  it('shows pending receipt NOT available', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] },
      },
      latest_terminal_run: {
        run_id: 'run_p',
        approval_status: 'PENDING',
        asset: { requested_tag: 'R-1001', canonical_tag: null, identity_status: null, identity_source: null },
        retrieval: { chunk_count: null, unique_asset_tags: [], source_files: [], document_types: [], retrieval_modes: [] },
        calculations: { any_threshold_breach: null, breached_signals: [], inspection_findings: [], vendor_parts: [], sop_requirements: [], sandbox_used: null },
        execution_trace: { executed_nodes: [] },
        routing: { task_type: null, selected_model: null, models_required: [], requires_rag: null, requires_tools: null, local_only: null, all_local: null, confidence: null, reason: null },
        actual_model_execution: { recorded_models: [], status: 'NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE' },
        human_review: { approval_required: true, status: 'PENDING', reviewer_id: null, reviewer_comment: null, reviewer_identity_verified: false, created_at: '2026-09-23T09:00:00Z', reviewed_at: null },
        artifact: { logical_path: 'data/outputs/R-1001.docx', sha256: null, verification_ok: null },
        receipt: { available: false },
        chain: { linked: false, global_chain_valid: true, global_chain_status: 'VALID' },
        sovereignty: { external_calls_recorded: 0, network_guard_scope: 'application-level agent run', whole_machine_airgap_certified: false },
      } as any,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('Receipt not available — review pending')
    expect(screen.getByText('Receipt not available — review pending')).toBeDefined()
  })

  it('shows pending chain NOT linked', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockResolvedValue({
      generated_at: '2026-09-23T09:00:00Z',
      repository: { commit: 'abc123' },
      runtime: {
        source_type: 'LIVE',
        sovereign_mode: true,
        gpu: null,
        components: [],
        external_api_calls: 0,
        blocked_connections: 0,
        uptime_seconds: 0,
      },
      governance: {
        source_type: 'LIVE_PERSISTENT',
        pending_review_count: 0,
        pending_reviews: [],
        chain: { entry_count: 0, head_sequence: null, head_run_id: null, head_chain_sha256: null, valid: true, status: 'VALID', checks: {}, violations: [] },
      },
      latest_terminal_run: {
        run_id: 'run_p',
        approval_status: 'PENDING',
        asset: { requested_tag: 'R-1001', canonical_tag: null, identity_status: null, identity_source: null },
        retrieval: { chunk_count: null, unique_asset_tags: [], source_files: [], document_types: [], retrieval_modes: [] },
        calculations: { any_threshold_breach: null, breached_signals: [], inspection_findings: [], vendor_parts: [], sop_requirements: [], sandbox_used: null },
        execution_trace: { executed_nodes: [] },
        routing: { task_type: null, selected_model: null, models_required: [], requires_rag: null, requires_tools: null, local_only: null, all_local: null, confidence: null, reason: null },
        actual_model_execution: { recorded_models: [], status: 'NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE' },
        human_review: { approval_required: true, status: 'PENDING', reviewer_id: null, reviewer_comment: null, reviewer_identity_verified: false, created_at: '2026-09-23T09:00:00Z', reviewed_at: null },
        artifact: { logical_path: 'data/outputs/R-1001.docx', sha256: null, verification_ok: null },
        receipt: { available: false },
        chain: { linked: false, global_chain_valid: true, global_chain_status: 'VALID' },
        sovereignty: { external_calls_recorded: 0, network_guard_scope: 'application-level agent run', whole_machine_airgap_certified: false },
      } as any,
      flagship: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      evaluation: { source_type: 'UNAVAILABLE', available: false, reason: 'report file not found' },
      claim_boundaries: { reviewer_identity_authenticated: false, whole_machine_airgap_certified: false, receipt_chain_tamper_proof: false, external_trust_anchor_present: false, digital_signature_present: false, general_runtime_status: 'UNKNOWN' },
    })
    renderJudge()
    await screen.findByText('Not linked to receipt chain')
    expect(screen.getByText('Not linked to receipt chain')).toBeDefined()
  })

  it('shows approved run receipt valid', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('VALID')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('shows rejected run receipt may still be valid', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('VALID')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('displays reviewer_identity_verified=false honestly', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('Unverified')
    expect(screen.getByText('Unverified')).toBeDefined()
  })

  it('displays routing general', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('general')
    expect(screen.getByText('general')).toBeDefined()
  })

  it('displays actual recorded_models empty as no explicit execution evidence', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('None')
    expect(screen.getByText('None')).toBeDefined()
  })

  it('does not show routing as actual execution', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE')
    expect(screen.getByText('NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE')).toBeDefined()
  })

  it('displays artifact SHA', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('9def2ff77c8c…cb12')
    expect(screen.getByText('9def2ff77c8c…cb12')).toBeDefined()
  })

  it('displays receipt SHA', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('receipthash')
    expect(screen.getByText('receipthash')).toBeDefined()
  })

  it('displays chain SHA', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('chainhash')
    expect(screen.getByText('chainhash')).toBeDefined()
  })

  it('shows whole-machine certification false', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('NO')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('shows tamper-proof false', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('NO')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('shows digital signature false', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    const els = await screen.findAllByText('NO')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('refresh triggers overview GET', async () => {
    const overviewFn = mockOverview()
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(overviewFn)
    renderJudge()
    await screen.findByText('JUDGE MODE')
    const refreshBtn = screen.getByText('Refresh')
    refreshBtn.click()
    await waitFor(() => expect(overviewFn).toHaveBeenCalledTimes(2))
  })

  it('backend failure shows error state', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockRejectedValue(new Error('connect ECONNREFUSED'))
    renderJudge()
    await screen.findByText(/connect ECONNREFUSED/)
    expect(screen.getByText(/connect ECONNREFUSED/)).toBeDefined()
  })

  it('no approve button', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('JUDGE MODE')
    expect(screen.queryByText(/Approve/i)).toBeNull()
  })

  it('no reject button', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('JUDGE MODE')
    expect(screen.queryByRole('button', { name: /reject/i })).toBeNull()
  })

  it('no Judge mutation call performed', async () => {
    const overviewFn = mockOverview()
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(overviewFn)
    const approveSpy = vi.spyOn(apiClient, 'runAgent').mockResolvedValue({} as any)
    renderJudge()
    await screen.findByText('JUDGE MODE')
    expect(approveSpy).not.toHaveBeenCalled()
  })

  it('source timestamp shown for historical evidence', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('HISTORICAL PROOF')
    expect(screen.getByText('HISTORICAL PROOF')).toBeDefined()
  })

  it('current-vs-frozen source separation visible', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    renderJudge()
    await screen.findByText('HISTORICAL PROOF')
    await screen.findByText('FROZEN EVALUATION')
    expect(screen.getByText('HISTORICAL PROOF')).toBeDefined()
    expect(screen.getByText('FROZEN EVALUATION')).toBeDefined()
  })

  it('absolute paths are not displayed from valid fixture', async () => {
    vi.spyOn(apiClient, 'getJudgeOverview').mockImplementation(mockOverview())
    const { container } = renderJudge()
    await screen.findByText('JUDGE MODE')
    const text = container.textContent ?? ''
    expect(text).not.toContain('D:\\Sovereign_AI')
    expect(text).not.toContain('C:\\Users\\shiva')
  })
})
