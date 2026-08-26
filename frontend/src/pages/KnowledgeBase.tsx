import { Upload, Search, FileText, CheckCircle } from 'lucide-react'

export default function KnowledgeBase() {
  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <div className="bg-background-secondary rounded-lg border border-border p-6">
        <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-accent-primary transition-colors cursor-pointer">
          <Upload className="w-8 h-8 mx-auto mb-3 text-text-secondary" />
          <p className="text-sm text-text-primary mb-1">Drop files here or click to browse</p>
          <p className="text-xs text-text-secondary">PDF, DOCX, XLSX, CSV, PNG, JPG, EML, MSG</p>
        </div>
      </div>

      {/* Search */}
      <div className="bg-background-secondary rounded-lg border border-border p-4">
        <div className="flex gap-2">
          <Search className="w-5 h-5 text-text-secondary mt-2" />
          <input
            type="text"
            placeholder="Search knowledge base..."
            className="flex-1 bg-background-tertiary border border-border rounded-md px-4 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent-primary"
          />
        </div>
      </div>

      {/* Document Library */}
      <div className="bg-background-secondary rounded-lg border border-border">
        <div className="p-4 border-b border-border">
          <h3 className="text-sm font-semibold text-text-primary">Document Library</h3>
        </div>
        <div className="divide-y divide-border">
          {[
            { name: 'Maintenance_SOP.pdf', type: 'SOP', status: 'Ready', chunks: 384 },
            { name: 'Safety_Manual.pdf', type: 'Manual', status: 'Ready', chunks: 512 },
            { name: 'Inspection_Report.pdf', type: 'Report', status: 'Ready', chunks: 96 },
            { name: 'Vendor_Emails.eml', type: 'Correspondence', status: 'Ready', chunks: 41 },
          ].map((doc, i) => (
            <div key={i} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-text-secondary" />
                <div>
                  <p className="text-sm text-text-primary">{doc.name}</p>
                  <p className="text-xs text-text-secondary">{doc.type} • {doc.chunks} chunks</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-3 h-3 text-accent-success" />
                <span className="text-xs text-accent-success">{doc.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
