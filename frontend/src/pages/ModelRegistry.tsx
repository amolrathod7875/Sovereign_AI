import { CheckCircle, Circle } from 'lucide-react'

export default function ModelRegistry() {
  const models = [
    { id: 'general', name: 'Qwen2.5-3B-Instruct', type: 'General LLM', status: 'ACTIVE', vram: '2.1 GB', capabilities: ['reasoning', 'tools', 'summarization'] },
    { id: 'coder', name: 'Qwen2.5-Coder-3B-Instruct', type: 'Coding LLM', status: 'STANDBY', vram: '2.4 GB', capabilities: ['code', 'debugging'] },
    { id: 'vision', name: 'Qwen-VL-3B', type: 'Vision LLM', status: 'OFFLINE', vram: '3.8 GB', capabilities: ['vision', 'image'] },
    { id: 'embedding', name: 'BGE-large-en-v1.5', type: 'Embedding', status: 'ONLINE', vram: '1.2 GB', capabilities: ['embedding'] },
  ]

  return (
    <div className="grid grid-cols-2 gap-4">
      {models.map(model => (
        <div key={model.id} className="bg-background-secondary rounded-lg border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">{model.name}</h3>
              <p className="text-xs text-text-secondary">{model.type}</p>
            </div>
            <div className={`flex items-center gap-1 text-xs ${model.status === 'ACTIVE' || model.status === 'ONLINE' ? 'text-accent-success' : 'text-text-secondary'}`}>
              {model.status === 'ACTIVE' || model.status === 'ONLINE' ? (
                <CheckCircle className="w-3 h-3" />
              ) : (
                <Circle className="w-3 h-3" />
              )}
              {model.status}
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-secondary">VRAM:</span>
              <span className="text-text-primary font-mono">{model.vram}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {model.capabilities.map(cap => (
                <span key={cap} className="text-xs px-2 py-0.5 bg-background-tertiary rounded text-text-secondary">
                  {cap}
                </span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
