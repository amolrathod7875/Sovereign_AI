import { useEffect, useState } from 'react'
import { CheckCircle, Cpu, Network, Shield } from 'lucide-react'
import { useSystemStore, summarizeModels } from '../lib/store'
import { apiClient } from '../lib/api/client'
import type { NetworkEvent } from '../lib/api/types'

export default function Dashboard() {
  const status = useSystemStore((s) => s.status)
  const models = useSystemStore((s) => s.models)
  const error = useSystemStore((s) => s.error)
  const [events, setEvents] = useState<NetworkEvent[]>([])

  useEffect(() => {
    apiClient.getNetworkEvents(10).then(setEvents).catch(() => setEvents([]))
  }, [])

  const modelSummary = summarizeModels(models)
  const externalCalls = status?.external_api_calls ?? 0
  const backendUp = !error && status !== null

  const services = (status?.components ?? []).map((c) => ({
    name: c.name,
    status: c.status === 'ONLINE' ? 'online' : c.status === 'NOT CONFIGURED' ? 'not-configured' : 'offline',
    model: '',
  }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-sovereign mb-2">
            <div className={backendUp ? 'w-2 h-2 rounded-full bg-accent-sovereign animate-pulse' : 'w-2 h-2 rounded-full bg-accent-danger'} />
            <span className="text-xs font-medium">{backendUp ? 'SOVEREIGN' : 'BACKEND OFFLINE'}</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{backendUp ? 'ACTIVE' : 'OFFLINE'}</p>
          <p className="text-xs text-text-secondary mt-1">External AI calls: {externalCalls}</p>
        </div>

        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-primary mb-2">
            <Cpu className="w-4 h-4" />
            <span className="text-xs font-medium">MODELS</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">
            {modelSummary.available}/{modelSummary.total}
          </p>
          <p className="text-xs text-text-secondary mt-1">Local models available</p>
        </div>

        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-success mb-2">
            <CheckCircle className="w-4 h-4" />
            <span className="text-xs font-medium">EXTERNAL</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{externalCalls}</p>
          <p className="text-xs text-text-secondary mt-1">Calls to non-local hosts</p>
        </div>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Components</h3>
        <div className="grid grid-cols-3 gap-4">
          {services.length === 0 && <p className="text-xs text-text-secondary">No component data.</p>}
          {services.map((service) => (
            <div key={service.name} className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  service.status === 'online' ? 'bg-accent-success' : service.status === 'not-configured' ? 'bg-text-secondary' : 'bg-accent-danger'
                }`}
              />
              <div>
                <p className="text-sm text-text-primary">{service.name}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
          <Network className="w-4 h-4" /> Network Log
        </h3>
        {events.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Shield className="w-4 h-4 text-accent-sovereign" />
            No outbound connections detected since system start.
          </div>
        ) : (
          <div className="space-y-1">
            {events.map((e) => (
              <div key={e.id} className="text-xs text-text-secondary font-mono">
                {e.timestamp} → {e.destination_host}:{e.destination_port} [{e.action}]
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
