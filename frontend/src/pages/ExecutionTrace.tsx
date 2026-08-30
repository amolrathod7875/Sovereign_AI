import { useEffect, useState } from 'react'
import { CheckCircle, AlertCircle, Clock } from 'lucide-react'
import { apiClient } from '../lib/api/client'
import { modelDisplayName } from '../lib/utils'
import type { RunSummary } from '../lib/api/types'

export default function ExecutionTrace() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    Promise.all([apiClient.listAgentRuns(50), apiClient.listCoderRuns(50)])
      .then(([agent, coder]) => {
        if (!alive) return
        const merged = [...agent, ...coder]
        merged.sort((a, b) => (b.run_id || '').localeCompare(a.run_id || ''))
        setRuns(merged)
      })
      .catch(() => {})
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="space-y-6">
      {loading && <p className="text-xs text-text-secondary">Loading executions…</p>}
      {!loading && runs.length === 0 && (
        <p className="text-xs text-text-secondary">No executions recorded yet in this backend process.</p>
      )}
      <div className="space-y-4">
        {runs.map((exec) => (
          <div key={exec.run_id} className="bg-background-secondary rounded-lg border border-border p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="font-mono text-xs text-text-secondary">{exec.run_id}</span>
                <h3 className="text-sm font-semibold text-text-primary">
                  {exec.task_type || 'TASK'}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {exec.status === 'success' || exec.status === 'COMPLETED' || exec.status === 'completed' ? (
                  <CheckCircle className="w-4 h-4 text-accent-success" />
                ) : exec.status === 'failed' || exec.status === 'FAILED' ? (
                  <AlertCircle className="w-4 h-4 text-accent-danger" />
                ) : (
                  <Clock className="w-4 h-4 text-accent-warning" />
                )}
                <span
                  className={`text-xs ${
                    exec.status === 'success' || exec.status === 'COMPLETED' || exec.status === 'completed'
                      ? 'text-accent-success'
                      : exec.status === 'failed' || exec.status === 'FAILED'
                        ? 'text-accent-danger'
                        : 'text-accent-warning'
                  }`}
                >
                  {exec.status}
                </span>
              </div>
            </div>
            <div className="flex gap-4 text-xs text-text-secondary">
              <span>Model: {modelDisplayName(exec.selected_model)}</span>
              <span>External calls: {exec.external_calls}</span>
              {exec.artifacts && exec.artifacts.length > 0 && <span>Artifacts: {exec.artifacts.length}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
