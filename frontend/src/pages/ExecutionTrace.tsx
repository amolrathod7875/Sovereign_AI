import { CheckCircle, Circle, Clock, AlertCircle } from 'lucide-react'

export default function ExecutionTrace() {
  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex gap-4">
        <select className="bg-background-secondary border border-border rounded-md px-4 py-2 text-sm text-text-primary">
          <option>All Tasks</option>
          <option>DOCUMENT_ANALYSIS</option>
          <option>DATA_ANALYSIS</option>
          <option>CODING</option>
        </select>
        <select className="bg-background-secondary border border-border rounded-md px-4 py-2 text-sm text-text-primary">
          <option>Today</option>
          <option>Last 7 days</option>
          <option>Last 30 days</option>
        </select>
      </div>

      {/* Execution List */}
      <div className="space-y-4">
        {[
          { id: 'EX-1042', task: 'Analyze inspection report', status: 'COMPLETED', duration: '14.8s', model: 'general' },
          { id: 'EX-1041', task: 'CSV downtime analysis', status: 'COMPLETED', duration: '8.2s', model: 'coder' },
          { id: 'EX-1040', task: 'Engineering image review', status: 'PARTIAL', duration: '5.1s', model: 'vision' },
        ].map(exec => (
          <div key={exec.id} className="bg-background-secondary rounded-lg border border-border p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="font-mono text-xs text-text-secondary">{exec.id}</span>
                <h3 className="text-sm font-semibold text-text-primary">{exec.task}</h3>
              </div>
              <div className="flex items-center gap-2">
                {exec.status === 'COMPLETED' && <CheckCircle className="w-4 h-4 text-accent-success" />}
                {exec.status === 'PARTIAL' && <AlertCircle className="w-4 h-4 text-accent-warning" />}
                <span className={`text-xs ${exec.status === 'COMPLETED' ? 'text-accent-success' : 'text-accent-warning'}`}>
                  {exec.status}
                </span>
              </div>
            </div>
            <div className="flex gap-4 text-xs text-text-secondary">
              <span>Duration: {exec.duration}</span>
              <span>Model: {exec.model}</span>
              <span>External calls: 0</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
