import { useEffect, useState, type FormEvent } from 'react'
import { Upload, Search, FileText, CheckCircle, Database, AlertTriangle } from 'lucide-react'
import { apiClient, ApiError } from '../lib/api/client'
import type { RagSearchResult, DocumentResponse, SupportedFormats } from '../lib/api/types'

export default function KnowledgeBase() {
  const [formats, setFormats] = useState<SupportedFormats | null>(null)
  const [docs, setDocs] = useState<DocumentResponse[]>([])
  const [docsError, setDocsError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [ingestLog, setIngestLog] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RagSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  useEffect(() => {
    apiClient.getSupportedFormats().then(setFormats).catch(() => setFormats(null))
    apiClient
      .listDocuments()
      .then(setDocs)
      .catch((e) => setDocsError(e instanceof ApiError ? e.detail : 'Document registry unavailable'))
  }, [])

  async function handleUpload(file: File | null) {
    if (!file) return
    setUploading(true)
    setIngestLog(null)
    try {
      const up = await apiClient.uploadDocument(file)
      setIngestLog(`Uploaded "${up.filename}" → stored locally.`)
      if (up.parse_supported) {
        try {
          await apiClient.ingestDocument(up.document_id)
          setIngestLog((p) => `${p} Ingestion started.`)
          apiClient.listDocuments().then(setDocs).catch(() => {})
        } catch (e) {
          setIngestLog((p) => `${p} Ingestion note: ${e instanceof ApiError ? e.detail : 'failed'}`)
        }
      } else {
        setIngestLog((p) => `${p} (vision-only format — not indexed into RAG.)`)
      }
    } catch (e) {
      setIngestLog(e instanceof ApiError ? e.detail : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setSearchError(null)
    try {
      const res = await apiClient.searchRag({ query, top_k: 8, asset_tag: 'R-1001' })
      setResults(res.results)
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.detail : 'Search failed')
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-background-secondary rounded-lg border border-border p-6">
        <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-accent-primary transition-colors">
          <label className="cursor-pointer flex flex-col items-center">
            <Upload className="w-8 h-8 mb-3 text-text-secondary" />
            <p className="text-sm text-text-primary mb-1">Drop files here or click to browse</p>
            <p className="text-xs text-text-secondary">
              {formats ? `Supported: ${formats.accept.join(', ').toUpperCase()} · max ${formats.max_file_mb}MB` : 'PDF, DOCX, XLSX, CSV, images, EML, MSG'}
            </p>
            <input type="file" className="hidden" onChange={(e) => handleUpload(e.target.files?.[0] ?? null)} />
          </label>
        </div>
        {uploading && <p className="text-xs text-text-secondary mt-2">Uploading…</p>}
        {ingestLog && (
          <p className="text-xs text-accent-success mt-2 flex items-center gap-1">
            <CheckCircle className="w-3 h-3" /> {ingestLog}
          </p>
        )}
      </div>

      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <Search className="w-5 h-5 text-text-secondary mt-2" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask the local knowledge base (e.g. maintenance requirements for R-1001)…"
            aria-label="Knowledge base query"
            className="flex-1 bg-background-tertiary border border-border rounded-md px-4 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent-primary"
          />
          <button
            type="submit"
            disabled={searching}
            className="px-4 py-2 rounded-md bg-accent-primary text-white text-sm disabled:opacity-50"
          >
            {searching ? 'Searching…' : 'Search'}
          </button>
        </form>
        {searchError && (
          <p className="text-xs text-accent-danger mt-2 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> {searchError}
          </p>
        )}
        {results.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-text-secondary">Retrieved {results.length} local chunks:</p>
            {results.map((r) => (
              <div key={r.chunk_id} className="bg-background-tertiary rounded p-2">
                <p className="text-xs text-text-primary">{r.text.slice(0, 280)}</p>
                <p className="text-[10px] text-text-secondary mt-1">
                  {r.source_file} · {r.document_type} · score {r.score.toFixed(3)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-background-secondary rounded-lg border border-border">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Database className="w-4 h-4 text-text-secondary" />
          <h3 className="text-sm font-semibold text-text-primary">Document Library</h3>
        </div>
        <div className="divide-y divide-border">
          {docsError && (
            <p className="p-4 text-xs text-accent-warning flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {docsError}
            </p>
          )}
          {!docsError && docs.length === 0 && (
            <p className="p-4 text-xs text-text-secondary">No documents in registry (PostgreSQL optional; RAG index may still be populated).</p>
          )}
          {docs.map((d) => (
            <div key={d.id} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-text-secondary" />
                <div>
                  <p className="text-sm text-text-primary">{d.filename}</p>
                  <p className="text-xs text-text-secondary">
                    {d.doc_type} · {d.chunks != null ? `${d.chunks} chunks` : 'unindexed'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-3 h-3 text-accent-success" />
                <span className="text-xs text-accent-success">{d.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
