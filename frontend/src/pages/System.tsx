import { useEffect, useState } from 'react'
import { useSystemStore } from '../lib/store'
import { StatusBadge } from '../components/common/StatusBadge'
import type { SystemStatus } from '../lib/api/types'

const EXPECTED = ['fastapi', 'agent', 'router', 'qwen-coder', 'vision', 'general', 'qdrant', 'bm25', 'postgres', 'networkguard']

export default function System() {
  const status = useSystemStore((s) => s.status)
  const error = useSystemStore((s) => s.error)
  const [local, setLocal] = useState<SystemStatus | null>(null)

  useEffect(() => {
    if (status) setLocal(status)
  }, [status])

  if (error && !local) {
    return (
      <div className="space-y-6">
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-accent-danger text-sm">
          Backend unavailable: {error}
        </div>
      </div>
    )
  }

  if (!local) {
    return <p className="text-xs text-text-secondary">Loading system status…</p>
  }

  const components = local.components ?? []
  const gpu = local.gpu

  return (
    <div className="space-y-6">
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Service Health</h3>
        <div className="grid grid-cols-2 gap-3">
          {EXPECTED.map((id) => {
            const c = components.find((x) => x.id === id)
            if (!c) return null
            return (
              <div key={id} className="flex items-center justify-between p-2 rounded bg-background-tertiary">
                <span className="text-sm text-text-primary">{c.name}</span>
                <StatusBadge status={c.status} label={c.status} />
              </div>
            )
          })}
        </div>
        <p className="text-[10px] text-text-secondary mt-3">{local.components.length} components probed</p>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Sovereignty</h3>
        <div className="flex items-center gap-2 mb-3">
          <span className={local.sovereign ? 'text-accent-sovereign' : 'text-accent-danger'}>
            {local.sovereign ? 'SOVEREIGN MODE ACTIVE' : 'SOVEREIGN MODE INACTIVE'}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <Metric label="External API calls" value={local.external_api_calls} good={local.external_api_calls === 0} />
          <Metric label="Blocked connections" value={local.blocked_connections} good />
          <Metric label="Uptime (s)" value={local.uptime_seconds} good />
        </div>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Hardware</h3>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-text-secondary">GPU</span>
            <span className="text-text-primary">{gpu?.name ?? 'not detected'}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-text-secondary">VRAM</span>
            <span className="text-text-primary">
              {gpu?.memory_used_gb != null ? `${gpu.memory_used_gb} / ${gpu.memory_total_gb} GB` : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value, good }: { label: string; value: number; good: boolean }) {
  return (
    <div className="bg-background-tertiary rounded p-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={good ? 'text-accent-success font-bold' : 'text-accent-danger font-bold'}>{value}</p>
    </div>
  )
}
