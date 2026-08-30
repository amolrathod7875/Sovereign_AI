import { describe, it, expect } from 'vitest'
import { apiClient, ApiError } from '../../src/lib/api/client'

/**
 * End-to-end checks against the REAL local Sovereign AI backend.
 *
 * Excluded from the unit run (`npm test`). Run with `npm run test:e2e` while the
 * FastAPI server is up on the configured origin. Backend reachability is probed
 * via a top-level await so `describe.skipIf` sees the real state at collection
 * time; if the backend is not reachable the suite is skipped honestly.
 *
 * Control-plane specs (health, system status, routing, upload, artifacts) require
 * only the FastAPI server. The model-inference specs (coder / agent / vision) need
 * the local llama.cpp servers on :8002/:8003; when those are not running the
 * backend returns a clear 4xx/5xx and the frontend must surface it — these specs
 * therefore assert a well-formed response OR a typed ApiError (no silent hang).
 */
let backendUp = false
try {
  await apiClient.getHealth()
  backendUp = true
} catch {
  backendUp = false
  console.warn('[e2e] Backend not reachable — skipping real-backend integration specs.')
}

/** Either a successful call (object) or a graceful backend error — never a hang. */
async function tolerant<T>(fn: () => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: ApiError }> {
  try {
    return { ok: true, value: await fn() }
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, error: e }
    throw e
  }
}

describe.skipIf(!backendUp)('Phase 6 E2E — real backend', () => {
  it('health reports sovereign mode', async () => {
    const h = await apiClient.getHealth()
    expect(h.status).toBe('healthy')
    expect(h.sovereign_mode).toBe(true)
  })

  it('system status probes components honestly (no invented availability)', async () => {
    const s = await apiClient.getSystemStatus()
    expect(Array.isArray(s.components)).toBe(true)
    expect(s.components.length).toBeGreaterThan(0)
    // a NOT CONFIGURED / UNAVAILABLE state must be reported as-is, not hidden
    expect(s.components.some((c) => c.id === 'postgres')).toBe(true)
  })

  it('document upload formats are reported from the backend', async () => {
    const f = await apiClient.getSupportedFormats()
    expect(Array.isArray(f.accept)).toBe(true)
    expect(f.accept.length).toBeGreaterThan(0)
  })

  it('routing a coding task selects the local coder model with zero external calls', async () => {
    const d = await apiClient.routeTask({ task: 'Write a Python function to calculate Reynolds number.' })
    expect(d.selected_model).toBe('qwen-coder')
    expect(d.external_calls).toBe(0)
  })

  it('uploading a local document returns a stored local path', async () => {
    const file = new File(['{"note":"sovereign ai e2e demo"}'], 'e2e_demo.json', { type: 'application/json' })
    const up = await apiClient.uploadDocument(file)
    expect(up.stored_path).toBeTruthy()
    expect(up.filename).toBe('e2e_demo.json')
  })

  it('artifacts endpoint lists local files (read-only)', async () => {
    const a = await apiClient.listArtifacts()
    expect(Array.isArray(a)).toBe(true)
  })

  it('coding task integrates with the local coder (or fails gracefully without the model server)', async () => {
    const r = await tolerant(() => apiClient.runCoder('Return the number 42.'))
    if (r.ok) expect(r.value.external_calls).toBe(0)
    else expect(r.error.status).toBeGreaterThanOrEqual(400)
  })

  it('knowledge/agent task integrates (or fails gracefully without the model server)', async () => {
    const r = await tolerant(() => apiClient.runAgent({ task: 'Explain the maintenance requirements for R-1001.', asset_tag: 'R-1001' }))
    if (r.ok) expect(r.value.external_calls).toBe(0)
    else expect(r.error.status).toBeGreaterThanOrEqual(400)
  })
})
