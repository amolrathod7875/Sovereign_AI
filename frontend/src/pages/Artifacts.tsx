import { useEffect, useState } from 'react'
import { FileText, FileSpreadsheet, FileCode, Download, FileImage, AlertTriangle } from 'lucide-react'
import { apiClient, ApiError } from '../lib/api/client'
import { formatBytes } from '../lib/utils'
import type { ArtifactInfo } from '../lib/api/types'

function getIcon(kind: string) {
  switch (kind) {
    case 'DOCX':
    case 'PDF':
      return FileText
    case 'XLSX':
      return FileSpreadsheet
    case 'CODE':
    case 'JSON':
    case 'CSV':
    case 'MARKDOWN':
    case 'TEXT':
      return FileCode
    case 'PPTX':
      return FileImage
    default:
      return FileText
  }
}

export default function Artifacts() {
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    apiClient
      .listArtifacts()
      .then((a) => alive && setArtifacts(a))
      .catch((e) => alive && setError(e instanceof ApiError ? e.detail : 'Failed to list artifacts'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="bg-background-secondary rounded-lg border border-border">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Artifacts</h3>
        <span className="text-xs text-text-secondary">{artifacts.length} generated locally</span>
      </div>
      {error && (
        <p className="p-4 text-xs text-accent-danger flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {error}
        </p>
      )}
      {loading && <p className="p-4 text-xs text-text-secondary">Loading…</p>}
      {!loading && !error && artifacts.length === 0 && (
        <p className="p-4 text-xs text-text-secondary">
          No artifacts yet. Run a task that produces a document (e.g. an approval-note request) in the Workbench.
        </p>
      )}
      <div className="divide-y divide-border">
        {artifacts.map((a) => {
          const Icon = getIcon(a.kind)
          return (
            <div key={a.artifact_id} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Icon className="w-5 h-5 text-text-secondary" />
                <div>
                  <p className="text-sm text-text-primary">{a.filename}</p>
                  <p className="text-xs text-text-secondary">
                    {a.kind} · {formatBytes(a.size)} · {a.run_id ?? '—'}
                  </p>
                </div>
              </div>
              <a
                href={apiClient.artifactDownloadUrl(a.artifact_id)}
                className="p-2 rounded-md hover:bg-background-tertiary text-text-secondary"
                aria-label={`Download ${a.filename}`}
              >
                <Download className="w-4 h-4" />
              </a>
            </div>
          )
        })}
      </div>
    </div>
  )
}
