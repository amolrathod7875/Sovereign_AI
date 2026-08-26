import { CheckCircle } from 'lucide-react'

export default function System() {
  const services = [
    { name: 'Backend API', status: 'HEALTHY' },
    { name: 'PostgreSQL', status: 'HEALTHY' },
    { name: 'Qdrant', status: 'HEALTHY' },
    { name: 'vLLM General', status: 'HEALTHY' },
    { name: 'vLLM Coder', status: 'HEALTHY' },
    { name: 'vLLM Vision', status: 'STANDBY' },
    { name: 'Piston', status: 'HEALTHY' },
    { name: 'OCR (PaddleOCR)', status: 'AVAILABLE' },
  ]

  return (
    <div className="space-y-6">
      {/* Service Health */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Service Health</h3>
        <div className="grid grid-cols-2 gap-4">
          {services.map(service => (
            <div key={service.name} className="flex items-center justify-between p-2">
              <span className="text-sm text-text-primary">{service.name}</span>
              <div className="flex items-center gap-1">
                <CheckCircle className={`w-3 h-3 ${service.status === 'HEALTHY' || service.status === 'AVAILABLE' ? 'text-accent-success' : 'text-accent-warning'}`} />
                <span className={`text-xs ${service.status === 'HEALTHY' || service.status === 'AVAILABLE' ? 'text-accent-success' : 'text-accent-warning'}`}>
                  {service.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hardware */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Hardware</h3>
        <div className="space-y-2">
          <div className="flex justify-between">
            <span className="text-sm text-text-secondary">GPU</span>
            <span className="text-sm text-text-primary">--</span>
          </div>
          <div className="flex justify-between">
            <span className="text-sm text-text-secondary">VRAM</span>
            <span className="text-sm text-text-primary">-- / 6 GB</span>
          </div>
          <div className="flex justify-between">
            <span className="text-sm text-text-secondary">Temperature</span>
            <span className="text-sm text-text-primary">--°C</span>
          </div>
        </div>
      </div>
    </div>
  )
}
