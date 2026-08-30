import { useEffect, useState } from 'react'
import { Shield, CheckCircle, XCircle, Activity } from 'lucide-react'
import { apiClient } from '../lib/api/client'
import { useSystemStore } from '../lib/store'
import type { NetworkEvent } from '../lib/api/types'

export default function NetworkMonitor() {
  const status = useSystemStore((s) => s.status)
  const [events, setEvents] = useState<NetworkEvent[]>([])

  useEffect(() => {
    let alive = true
    const load = () => apiClient.getNetworkEvents(100).then((e) => alive && setEvents(e)).catch(() => {})
    load()
    const id = window.setInterval(load, 5000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  const externalCalls = status?.external_api_calls ?? 0
  const blocked = status?.blocked_connections ?? 0

  return (
    <div className="space-y-6">
      <div className="bg-background-secondary rounded-lg border border-border p-6 text-center">
        <div className="flex items-center justify-center gap-2 text-accent-sovereign mb-4">
          <Shield className="w-8 h-8" />
          <span className="text-xl font-bold">SOVEREIGN RUNTIME</span>
        </div>
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-3 h-3 rounded-full bg-accent-sovereign animate-pulse" />
          <span className="text-lg font-bold text-text-primary">LOCAL / AIR-GAPPED</span>
        </div>
        <p className="text-xs text-text-secondary">
          Status is reported by the backend probe — localhost/loopback traffic is not counted as external.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-success">{externalCalls}</p>
          <p className="text-xs text-text-secondary">External AI Calls</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-primary">{blocked}</p>
          <p className="text-xs text-text-secondary">Blocked Connections</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-text-primary">local</p>
          <p className="text-xs text-text-secondary">Connection Scope</p>
        </div>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Activity className="w-4 h-4 text-text-secondary" />
          <h3 className="text-sm font-semibold text-text-primary">Connection Log</h3>
        </div>
        <div className="p-4">
          {events.length === 0 ? (
            <div className="text-center py-6">
              <CheckCircle className="w-12 h-12 mx-auto mb-3 text-accent-success opacity-50" />
              <p className="text-sm text-text-secondary">No outbound connections detected since system start</p>
            </div>
          ) : (
            <div className="space-y-1">
              {events.map((e) => (
                <div key={e.id} className="flex items-center gap-2 text-xs font-mono">
                  {e.action === 'BLOCKED' ? (
                    <XCircle className="w-3 h-3 text-accent-danger" />
                  ) : (
                    <CheckCircle className="w-3 h-3 text-text-secondary" />
                  )}
                  <span className="text-text-primary">
                    {e.timestamp} → {e.destination_host}:{e.destination_port} [{e.action}]
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
