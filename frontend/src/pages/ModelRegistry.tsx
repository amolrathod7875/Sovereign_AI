import { useEffect, useState } from 'react'
import { CheckCircle, Circle, Cpu } from 'lucide-react'
import clsx from 'clsx'
import { apiClient, ApiError } from '../lib/api/client'
import { statusTone } from '../lib/utils'
import type { ModelInfo } from '../lib/api/types'

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    apiClient
      .listModels()
      .then((m) => alive && setModels(m))
      .catch((e) => alive && setError(e instanceof ApiError ? e.detail : 'Failed to load models'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="space-y-4">
      {error && (
        <div className="text-xs text-accent-danger bg-accent-danger/10 border border-accent-danger/30 rounded p-2">
          {error}
        </div>
      )}
      {loading && <p className="text-xs text-text-secondary">Loading models…</p>}
      <div className="grid grid-cols-2 gap-4">
        {models.map((model) => {
          const tone = statusTone(model.status)
          const online = model.status === 'online' || model.status === 'active'
          return (
            <div key={model.id} className="bg-background-secondary rounded-lg border border-border p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-text-secondary" />
                    {model.name}
                  </h3>
                  <p className="text-xs text-text-secondary">
                    {model.id} · {model.endpoint}
                  </p>
                </div>
                <div className={clsx('flex items-center gap-1 text-xs', tone.text)}>
                  {online ? <CheckCircle className="w-3 h-3" /> : <Circle className="w-3 h-3" />}
                  {tone.label}
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">VRAM:</span>
                  <span className="text-text-primary font-mono">
                    {model.vram_gb != null ? `${model.vram_gb} GB` : '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">Local:</span>
                  <span className={model.local ? 'text-accent-success' : 'text-accent-danger'}>
                    {model.local ? 'YES' : 'NO'}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {model.capabilities.map((cap) => (
                    <span key={cap} className="text-xs px-2 py-0.5 bg-background-tertiary rounded text-text-secondary">
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
