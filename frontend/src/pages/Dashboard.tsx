import { CheckCircle, Cpu, Database, Network } from 'lucide-react'

export default function Dashboard() {
  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-sovereign mb-2">
            <div className="w-2 h-2 rounded-full bg-accent-sovereign animate-pulse" />
            <span className="text-xs font-medium">SOVEREIGN</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">ACTIVE</p>
          <p className="text-xs text-text-secondary mt-1">External AI calls: 0</p>
        </div>

        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-primary mb-2">
            <Cpu className="w-4 h-4" />
            <span className="text-xs font-medium">GPU</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">--</p>
          <p className="text-xs text-text-secondary mt-1">Memory: --</p>
        </div>

        <div className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center gap-2 text-accent-success mb-2">
            <CheckCircle className="w-4 h-4" />
            <span className="text-xs font-medium">SERVICES</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">6/6</p>
          <p className="text-xs text-text-secondary mt-1">All systems operational</p>
        </div>
      </div>

      {/* Services Grid */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Services</h3>
        <div className="grid grid-cols-3 gap-4">
          {[
            { name: 'vLLM General', status: 'online', model: 'Qwen2.5-3B' },
            { name: 'vLLM Coder', status: 'online', model: 'Qwen2.5-Coder' },
            { name: 'Qdrant', status: 'online', model: '' },
            { name: 'PostgreSQL', status: 'online', model: '' },
            { name: 'Piston', status: 'online', model: '' },
            { name: 'Frontend', status: 'online', model: '' },
          ].map(service => (
            <div key={service.name} className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${service.status === 'online' ? 'bg-accent-success' : 'bg-accent-danger'}`} />
              <div>
                <p className="text-sm text-text-primary">{service.name}</p>
                {service.model && <p className="text-xs text-text-secondary">{service.model}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Recent Activity</h3>
        <div className="space-y-2">
          {[
            { action: 'Inspection report analyzed', time: '2 min ago', status: 'success' },
            { action: 'approval_note.docx generated', time: '2 min ago', status: 'success' },
            { action: 'CSV analysis verified', time: '8 min ago', status: 'success' },
            { action: 'Engineering image analyzed', time: '21 min ago', status: 'success' },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              {item.status === 'success' && <CheckCircle className="w-3 h-3 text-accent-success" />}
              <span className="text-text-primary">{item.action}</span>
              <span className="text-xs text-text-secondary">{item.time}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Network Status */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Network Status</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-text-secondary">External AI calls:</span>
            <span className="text-sm font-bold text-accent-success">0</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-text-secondary">Blocked attempts:</span>
            <span className="text-sm font-bold text-text-primary">0</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-text-secondary">Local traffic:</span>
            <span className="text-sm font-bold text-accent-success">healthy</span>
          </div>
        </div>
      </div>
    </div>
  )
}
