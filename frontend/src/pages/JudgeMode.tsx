import { useEffect, useMemo, useState, useCallback } from 'react'
import { ShieldCheck, RefreshCw } from 'lucide-react'
import { apiClient } from '../lib/api/client'
import type { JudgeOverview, JudgeRunDetail } from '../lib/api/types'
import { cn, statusTone } from '../lib/utils'
import SourceBadge from '../components/judge/SourceBadge'
import HashValue from '../components/judge/HashValue'
import EvidenceCard from '../components/judge/EvidenceCard'
import EvidenceFlow from '../components/judge/EvidenceFlow'

export default function JudgeMode() {
  const [overview, setOverview] = useState<JudgeOverview | null>(null)
  const [selectedRun, setSelectedRun] = useState<JudgeRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)

  const loadOverview = useCallback(async () => {
    setError(null)
    try {
      const data = await apiClient.getJudgeOverview()
      setOverview(data)
      setLastRefreshed(new Date())
      if (data.latest_terminal_run) {
        setSelectedRun((prev) => prev ?? data.latest_terminal_run)
      } else if (data.governance.pending_reviews.length > 0) {
        setSelectedRun((prev) => prev ?? null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Judge evidence unavailable — local backend unreachable')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    void loadOverview()
    const id = window.setInterval(() => {
      void loadOverview()
    }, 15000)
    return () => window.clearInterval(id)
  }, [loadOverview])

  const handleRefresh = () => {
    if (refreshing) return
    setRefreshing(true)
    setLoading(true)
    void loadOverview()
  }

  const selectRun = async (runId: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.getJudgeRun(runId)
      setSelectedRun(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run detail')
    } finally {
      setLoading(false)
    }
  }

  const runtimeComponents = useMemo(() => {
    if (!overview) return []
    return overview.runtime.components
  }, [overview])

  const generalStatus = runtimeComponents.find((c) => c.id === 'general')?.status ?? 'UNKNOWN'
  const visionStatus = runtimeComponents.find((c) => c.id === 'vision')?.status ?? 'UNKNOWN'
  const coderStatus = runtimeComponents.find((c) => c.id === 'qwen-coder')?.status ?? 'UNKNOWN'
  const qdrantStatus = runtimeComponents.find((c) => c.id === 'qdrant')?.status ?? 'UNKNOWN'
  const bm25Status = runtimeComponents.find((c) => c.id === 'bm25')?.status ?? 'UNKNOWN'

  const externalCalls = overview?.runtime.external_api_calls ?? 0
  const pendingCount = overview?.governance.pending_review_count ?? 0
  const chain = overview?.governance.chain
  const latestTerminal = overview?.latest_terminal_run ?? null
  const pendingRuns = overview?.governance.pending_reviews ?? []

  const selectedRunId = selectedRun?.run_id ?? null

  if (loading && !overview) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-text-primary flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-accent-sovereign" />
              JUDGE MODE
            </h1>
            <p className="text-xs text-text-secondary mt-1">Loading live evidence…</p>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-24 rounded-lg border border-border bg-background-secondary animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error && !overview) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-text-primary flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-accent-sovereign" />
              JUDGE MODE
            </h1>
            <p className="text-xs text-text-secondary mt-1">Evidence-backed sovereign industrial AI</p>
          </div>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border text-xs text-text-secondary hover:text-text-primary hover:bg-background-tertiary transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
        <div className="bg-accent-danger/10 border border-accent-danger/40 rounded-lg p-4 text-sm text-accent-danger">{error}</div>
      </div>
    )
  }

  if (!overview) return null

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-text-primary flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-accent-sovereign" />
            JUDGE MODE
          </h1>
          <p className="text-xs text-text-secondary mt-1">Evidence-backed sovereign industrial AI</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-text-secondary">
            {lastRefreshed ? `Updated ${lastRefreshed.toLocaleTimeString()}` : ''}
          </span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border text-xs text-text-secondary hover:text-text-primary hover:bg-background-tertiary transition-colors disabled:opacity-50"
          >
            <RefreshCw className={['w-3.5 h-3.5', refreshing && 'animate-spin'].join(' ')} />
            Refresh
          </button>
          <span className="inline-flex items-center px-2 py-0.5 rounded border border-border text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            READ ONLY
          </span>
          <span className="inline-flex items-center px-2 py-0.5 rounded border border-accent-sovereign/40 text-[10px] font-semibold uppercase tracking-wide text-accent-sovereign">
            LOCAL EVIDENCE
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-accent-danger/10 border border-accent-danger/40 rounded-lg p-3 text-xs text-accent-danger flex items-center justify-between">
          <span>{error}</span>
          <button onClick={handleRefresh} className="underline">Retry</button>
        </div>
      )}

      {/* Row 1 — Live Sovereignty */}
      <div className="flex items-center gap-2" data-testid="runtime-section">
        <h2 className="text-sm font-semibold text-text-primary">LIVE SOVEREIGNTY</h2>
        <SourceBadge source_type={overview.runtime.source_type} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <EvidenceCard title="General Model" badge={<StatusPill status={generalStatus} />}>
          <p className="text-xs text-text-secondary">Registered ≠ runtime available</p>
        </EvidenceCard>
        <EvidenceCard title="Vision Model" badge={<StatusPill status={visionStatus} />}>
          <p className="text-xs text-text-secondary">{visionStatus === 'OFFLINE' ? 'Weights present, no server' : '—'}</p>
        </EvidenceCard>
        <EvidenceCard title="Coder Model" badge={<StatusPill status={coderStatus} />}>
          <p className="text-xs text-text-secondary">{coderStatus === 'OFFLINE' ? 'Weights present, no server' : '—'}</p>
        </EvidenceCard>
        <EvidenceCard title="Hybrid RAG" badge={<span className="text-[10px] font-medium text-text-secondary">{qdrantStatus === 'ONLINE' && bm25Status === 'ONLINE' ? 'HYBRID' : 'DEGRADED'}</span>}>
          <div className="flex items-center gap-3 text-xs">
            <span className={qdrantStatus === 'ONLINE' ? 'text-accent-success' : 'text-accent-warning'}>Qdrant {qdrantStatus}</span>
            <span className={bm25Status === 'ONLINE' ? 'text-accent-success' : 'text-accent-warning'}>BM25 {bm25Status}</span>
          </div>
        </EvidenceCard>
        <EvidenceCard title="GPU">
          <p className="text-xs text-text-primary font-mono">{overview.runtime.gpu?.name ?? 'Not detected'}</p>
          {overview.runtime.gpu?.memory_used_gb != null && (
            <p className="text-[10px] text-text-secondary mt-1">
              {overview.runtime.gpu.memory_used_gb}/{overview.runtime.gpu.memory_total_gb} GB
            </p>
          )}
        </EvidenceCard>
        <EvidenceCard title="External Calls" badge={<span className="text-[10px] font-medium text-text-secondary">Current process</span>}>
          <p className="text-xl font-bold text-text-primary">{externalCalls}</p>
          <p className="text-[10px] text-text-secondary mt-1">Recorded by backend probe</p>
        </EvidenceCard>
        <EvidenceCard title="Pending Reviews">
          <p className="text-xl font-bold text-text-primary">{pendingCount}</p>
          <p className="text-[10px] text-text-secondary mt-1">Awaiting human approval</p>
        </EvidenceCard>
        <EvidenceCard title="Hash Chain" tone={chain?.valid ? 'success' : 'danger'}>
          <p className="text-sm font-medium text-text-primary">{chain?.valid ? 'VALID' : 'INVALID'}</p>
          <p className="text-[10px] text-text-secondary mt-1">
            {chain?.entry_count ?? 0} entries {chain?.head_run_id ? `· Head ${chain.head_run_id}` : ''}
          </p>
          {!chain?.valid && chain?.violations && chain.violations.length > 0 && (
            <p className="text-[10px] text-accent-danger mt-1 truncate" title={chain.violations[0]}>
              {chain.violations[0]}
            </p>
          )}
        </EvidenceCard>
      </div>

      {/* Row 2 — Run selector + detail */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Selected Run</span>
          {latestTerminal && (
            <button
              onClick={() => { setSelectedRun(latestTerminal) }}
              className={cn(
                'px-2 py-1 rounded border text-xs font-mono transition-colors',
                selectedRunId === latestTerminal.run_id
                  ? 'border-accent-primary text-accent-primary bg-accent-primary/10'
                  : 'border-border text-text-secondary hover:text-text-primary',
              )}
            >
              LATEST TERMINAL {latestTerminal.run_id}
            </button>
          )}
          {pendingRuns.map((r) => (
            <button
              key={r.run_id}
              onClick={() => void selectRun(r.run_id)}
              className={cn(
                'px-2 py-1 rounded border text-xs font-mono transition-colors',
                selectedRunId === r.run_id
                  ? 'border-accent-warning text-accent-warning bg-accent-warning/10'
                  : 'border-border text-text-secondary hover:text-text-primary',
              )}
            >
              PENDING {r.run_id}
            </button>
          ))}
          {!latestTerminal && pendingRuns.length === 0 && (
            <span className="text-xs text-text-secondary">No runs available</span>
          )}
        </div>

        {selectedRun ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <SourceBadge source_type="LIVE_PERSISTENT" />
              <span className="text-xs text-text-secondary">Run detail</span>
            </div>

            <EvidenceFlow run={selectedRun} />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <EvidenceCard title="Asset Identity">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Requested</span><span className="text-text-primary font-mono">{selectedRun.asset.requested_tag ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Canonical</span><span className="text-text-primary font-mono">{selectedRun.asset.canonical_tag ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Status</span><StatusPill status={selectedRun.asset.identity_status ?? 'UNKNOWN'} /></div>
                </div>
              </EvidenceCard>

              <EvidenceCard title="Human Review">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Status</span><StatusPill status={selectedRun.human_review.status} /></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Reviewer</span><span className="text-text-primary font-mono">{selectedRun.human_review.reviewer_id ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Identity</span><span className="text-text-secondary">{selectedRun.human_review.reviewer_identity_verified ? 'Verified' : 'Unverified'}</span></div>
                </div>
              </EvidenceCard>

              <EvidenceCard title="Sovereignty">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">External calls</span><span className="text-text-primary font-mono">{selectedRun.sovereignty.external_calls_recorded}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Air-gap certified</span><span className="text-text-secondary">{selectedRun.sovereignty.whole_machine_airgap_certified ? 'Yes' : 'No'}</span></div>
                </div>
              </EvidenceCard>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <EvidenceCard title="Retrieval">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Chunks</span><span className="text-text-primary font-mono">{selectedRun.retrieval.chunk_count ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Modes</span><span className="text-text-primary">{(selectedRun.retrieval.retrieval_modes ?? []).join(', ') || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Source files</span><span className="text-text-primary">{selectedRun.retrieval.source_files.length}</span></div>
                </div>
              </EvidenceCard>

              <EvidenceCard title="Calculations / Tools">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Threshold breach</span><StatusPill status={selectedRun.calculations.any_threshold_breach ? 'ONLINE' : 'OFFLINE'} /></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Sandbox</span><span className="text-text-primary">{selectedRun.calculations.sandbox_used ? 'Used' : 'Not recorded'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Findings</span><span className="text-text-primary">{selectedRun.calculations.inspection_findings.length}</span></div>
                </div>
              </EvidenceCard>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <EvidenceCard title="Routing Decision">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Selected model</span><span className="text-text-primary font-mono">{selectedRun.routing.selected_model ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Task type</span><span className="text-text-primary">{selectedRun.routing.task_type ?? '—'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">RAG required</span><span className="text-text-primary">{selectedRun.routing.requires_rag ? 'Yes' : 'No'}</span></div>
                </div>
              </EvidenceCard>

              <EvidenceCard title="Actual Model Execution">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between"><span className="text-text-secondary">Recorded models</span><span className="text-text-primary">{selectedRun.actual_model_execution.recorded_models.length > 0 ? selectedRun.actual_model_execution.recorded_models.join(', ') : 'None'}</span></div>
                  <div className="flex justify-between"><span className="text-text-secondary">Status</span><span className="text-text-secondary">{selectedRun.actual_model_execution.status}</span></div>
                </div>
              </EvidenceCard>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <EvidenceCard title="Artifact">
                <div className="space-y-2">
                  <div className="text-xs text-text-secondary break-all">Path: {selectedRun.artifact.logical_path}</div>
                  <HashValue value={selectedRun.artifact.sha256} label="SHA256" />
                  <div className="flex justify-between text-xs">
                    <span className="text-text-secondary">Verified</span>
                    <span className={selectedRun.artifact.verification_ok ? 'text-accent-success' : 'text-accent-danger'}>
                      {selectedRun.artifact.verification_ok ? 'Yes' : 'No'}
                    </span>
                  </div>
                </div>
              </EvidenceCard>

              <EvidenceCard title="Receipt">
                {selectedRun.receipt.available ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className={selectedRun.receipt.valid ? 'text-accent-success' : 'text-accent-danger'}>
                        {selectedRun.receipt.valid ? 'VALID' : 'INVALID'}
                      </span>
                    </div>
                    <HashValue value={selectedRun.receipt.receipt_id} label="Receipt ID" />
                    <HashValue value={selectedRun.receipt.receipt_sha256} label="Receipt SHA256" />
                  </div>
                ) : (
                  <p className="text-xs text-text-secondary">Receipt not available — review pending</p>
                )}
              </EvidenceCard>
            </div>

            <EvidenceCard title="Hash Chain">
              {selectedRun.chain.linked ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={selectedRun.chain.global_chain_valid ? 'text-accent-success' : 'text-accent-danger'}>
                      {selectedRun.chain.global_chain_status}
                    </span>
                    <span className="text-xs text-text-secondary">Sequence #{selectedRun.chain.sequence_no}</span>
                  </div>
                  <HashValue value={selectedRun.chain.previous_chain_sha256} label="Previous" />
                  <HashValue value={selectedRun.chain.chain_sha256} label="Current" />
                </div>
              ) : (
                <p className="text-xs text-text-secondary">Not linked to receipt chain</p>
              )}
            </EvidenceCard>
          </div>
        ) : (
          <EvidenceCard title="Selected Run">
            <p className="text-xs text-text-secondary">Select a run from above to inspect evidence.</p>
          </EvidenceCard>
        )}
      </div>

      {/* Row 3 — Flagship Proof */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-text-primary">FLAGSHIP INDUSTRIAL VALIDATION</h2>
          <SourceBadge source_type={overview.flagship.source_type} />
        </div>
        {overview.flagship.available ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <EvidenceCard title="Asset"><p className="text-sm text-text-primary font-mono">{overview.flagship.asset ?? '—'}</p></EvidenceCard>
            <EvidenceCard title="Identity Status"><StatusPill status={overview.flagship.identity_status ?? 'UNKNOWN'} /></EvidenceCard>
            <EvidenceCard title="Retrieval"><p className="text-sm text-text-primary">{overview.flagship.retrieval_mode ?? '—'} · {overview.flagship.chunk_count ?? 0} chunks</p></EvidenceCard>
            <EvidenceCard title="Sandbox"><StatusPill status={overview.flagship.sandbox_used ? 'ONLINE' : 'OFFLINE'} /></EvidenceCard>
            <EvidenceCard title="External Calls"><p className="text-sm text-text-primary font-mono">{overview.flagship.external_calls ?? 0}</p></EvidenceCard>
            <EvidenceCard title="Artifact Verified"><StatusPill status={overview.flagship.artifact_verified ? 'ONLINE' : 'OFFLINE'} /></EvidenceCard>
            <EvidenceCard title="Validation">
              <p className="text-sm text-text-primary">
                {overview.flagship.validation_checks_passed ?? 0}/{overview.flagship.validation_checks_total ?? 0}
              </p>
            </EvidenceCard>
            <EvidenceCard title="Evidence Captured">
              <p className="text-xs text-text-secondary">{overview.flagship.timestamp ? new Date(overview.flagship.timestamp).toLocaleString() : '—'}</p>
              <p className="text-[10px] text-text-secondary mt-1">Historical validation — not current execution</p>
            </EvidenceCard>
          </div>
        ) : (
          <div className="bg-background-secondary rounded-lg border border-border p-4 text-xs text-text-secondary">
            FLAGSHIP EVIDENCE UNAVAILABLE — {overview.flagship.reason ?? 'report file not found'}
          </div>
        )}
      </div>

      {/* Row 4 — Evaluation */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-text-primary">FROZEN COMPETITION EVIDENCE</h2>
          <SourceBadge source_type={overview.evaluation.source_type} />
        </div>
        {overview.evaluation.available ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <EvidenceCard title="Industrial Golden"><p className="text-sm text-text-primary font-mono">{overview.evaluation.industrial?.passed ?? 0}/{overview.evaluation.industrial?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Asset Identity"><p className="text-sm text-text-primary font-mono">{overview.evaluation.asset_identity?.passed ?? 0}/{overview.evaluation.asset_identity?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Routing"><p className="text-sm text-text-primary font-mono">{overview.evaluation.routing?.passed ?? 0}/{overview.evaluation.routing?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Runtime Resilience"><p className="text-sm text-text-primary font-mono">{overview.evaluation.runtime_resilience?.passed ?? 0}/{overview.evaluation.runtime_resilience?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Security Controls"><p className="text-sm text-text-primary font-mono">{overview.evaluation.sovereignty_security?.passed ?? 0}/{overview.evaluation.sovereignty_security?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Artifact / Sandbox"><p className="text-sm text-text-primary font-mono">{overview.evaluation.artifact_sandbox?.passed ?? 0}/{overview.evaluation.artifact_sandbox?.total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Flagship Validation"><p className="text-sm text-text-primary font-mono">{overview.evaluation.flagship?.checks_passed ?? 0}/{overview.evaluation.flagship?.checks_total ?? 0}</p></EvidenceCard>
              <EvidenceCard title="Snapshot Generated">
                <p className="text-xs text-text-secondary">{overview.evaluation.generated_at ? new Date(overview.evaluation.generated_at).toLocaleString() : '—'}</p>
                <p className="text-[10px] text-text-secondary mt-1">Source: {overview.evaluation.source_repository_commit?.slice(0, 8) ?? '—'}</p>
              </EvidenceCard>
            </div>

            <EvidenceCard title="RAG Retrieval Metrics" tone="info">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div><span className="text-text-secondary">Hit@1</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.hit_at_1 ?? 0}/{overview.evaluation.rag?.queries_total ?? 0}</p></div>
                <div><span className="text-text-secondary">Hit@3</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.hit_at_3 ?? 0}/{overview.evaluation.rag?.queries_total ?? 0}</p></div>
                <div><span className="text-text-secondary">Hit@5</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.hit_at_5 ?? 0}/{overview.evaluation.rag?.queries_total ?? 0}</p></div>
                <div><span className="text-text-secondary">MRR</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.mrr ?? 0}</p></div>
                <div><span className="text-text-secondary">Primary source @1</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.primary_source_at_1 ?? 0}/{overview.evaluation.rag?.queries_total ?? 0}</p></div>
                <div><span className="text-text-secondary">Foreign asset hits</span><p className="text-text-primary font-mono">{overview.evaluation.rag?.foreign_asset_hits ?? 0}</p></div>
              </div>
            </EvidenceCard>
          </div>
        ) : (
          <div className="bg-background-secondary rounded-lg border border-border p-4 text-xs text-text-secondary">
            EVALUATION EVIDENCE UNAVAILABLE — {overview.evaluation.reason ?? 'report file not found'}
          </div>
        )}
      </div>

      {/* Row 5 — Claim Boundaries */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Scope Boundaries</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {([
            { label: 'Reviewer identity authenticated', value: overview.claim_boundaries.reviewer_identity_authenticated },
            { label: 'Whole-machine air-gap certified', value: overview.claim_boundaries.whole_machine_airgap_certified },
            { label: 'Chain tamper-proof', value: overview.claim_boundaries.receipt_chain_tamper_proof },
            { label: 'External trust anchor', value: overview.claim_boundaries.external_trust_anchor_present },
            { label: 'Digital signature', value: overview.claim_boundaries.digital_signature_present },
          ]).map((item) => (
            <div key={item.label} className="bg-background-secondary rounded-lg border border-border p-3">
              <p className="text-[10px] text-text-secondary mb-1">{item.label}</p>
              <p className={item.value ? 'text-accent-success text-sm font-medium' : 'text-text-secondary text-sm font-medium'}>
                {item.value ? 'YES' : 'NO'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatusPill({ status, className }: { status: string; className?: string }) {
  const tone = statusTone(status as any)
  return (
    <span className={['inline-flex items-center gap-1.5 text-xs font-medium', tone.text, className].join(' ')}>
      <span className={['w-1.5 h-1.5 rounded-full', tone.dot].join(' ')} />
      {status}
    </span>
  )
}
