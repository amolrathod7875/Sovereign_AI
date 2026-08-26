import { Shield, CheckCircle, XCircle } from 'lucide-react'

export default function NetworkMonitor() {
  return (
    <div className="space-y-6">
      {/* Sovereignty Status */}
      <div className="bg-background-secondary rounded-lg border border-border p-6 text-center">
        <div className="flex items-center justify-center gap-2 text-accent-sovereign mb-4">
          <Shield className="w-8 h-8" />
          <span className="text-xl font-bold">SOVEREIGN RUNTIME</span>
        </div>
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-3 h-3 rounded-full bg-accent-sovereign animate-pulse" />
          <span className="text-lg font-bold text-text-primary">AIR-GAPPED / LOCAL</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-success">0</p>
          <p className="text-xs text-text-secondary">External AI Calls</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-text-primary">0</p>
          <p className="text-xs text-text-secondary">Blocked Connections</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-primary">--</p>
          <p className="text-xs text-text-secondary">Local Connections</p>
        </div>
      </div>

      {/* Connection Log */}
      <div className="bg-background-secondary rounded-lg border border-border">
        <div className="p-4 border-b border-border">
          <h3 className="text-sm font-semibold text-text-primary">Connection Log</h3>
        </div>
        <div className="p-8 text-center">
          <CheckCircle className="w-12 h-12 mx-auto mb-3 text-accent-success opacity-50" />
          <p className="text-sm text-text-secondary">No outbound connections detected since system start</p>
          <p className="text-xs text-text-secondary mt-1">System started: --</p>
        </div>
      </div>
    </div>
  )
}
