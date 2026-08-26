import { FileText, FileSpreadsheet, FileCode, Download } from 'lucide-react'

export default function Artifacts() {
  const artifacts = [
    { name: 'approval_note.docx', type: 'DOCX', created: '2 min ago', execution: 'EX-1042' },
    { name: 'downtime_analysis.py', type: 'PY', created: '8 min ago', execution: 'EX-1041' },
    { name: 'downtime_analysis.xlsx', type: 'XLSX', created: '8 min ago', execution: 'EX-1041' },
    { name: 'board_presentation.pptx', type: 'PPTX', created: '21 min ago', execution: 'EX-1040' },
  ]

  const getIcon = (type: string) => {
    switch (type) {
      case 'DOCX': return FileText
      case 'XLSX': return FileSpreadsheet
      case 'PY': return FileCode
      case 'PPTX': return FileText
      default: return FileText
    }
  }

  return (
    <div className="bg-background-secondary rounded-lg border border-border">
      <div className="p-4 border-b border-border">
        <h3 className="text-sm font-semibold text-text-primary">Artifacts</h3>
      </div>
      <div className="divide-y divide-border">
        {artifacts.map((artifact, i) => {
          const Icon = getIcon(artifact.type)
          return (
            <div key={i} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Icon className="w-5 h-5 text-text-secondary" />
                <div>
                  <p className="text-sm text-text-primary">{artifact.name}</p>
                  <p className="text-xs text-text-secondary">{artifact.type} • {artifact.created} • {artifact.execution}</p>
                </div>
              </div>
              <button className="p-2 rounded-md hover:bg-background-tertiary text-text-secondary">
                <Download className="w-4 h-4" />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
