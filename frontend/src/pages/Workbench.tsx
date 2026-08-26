import { useState } from 'react'
import { Send, Paperclip, Upload, FileText, CheckCircle } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Array<{ document: string; page: number }>
  artifactId?: string
  artifactFilename?: string
}

const mockSources = [
  { document: 'Maintenance_SOP.pdf', page: 17 },
  { document: 'Maintenance_SOP.pdf', page: 23 },
]

export default function Workbench() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [steps, setSteps] = useState<Array<{ name: string; status: string }>>([])
  const [externalCalls, setExternalCalls] = useState(0)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isProcessing) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsProcessing(true)
    setSteps([])

    // Simulate agent workflow
    const workflowSteps = [
      { name: 'Task classified', status: 'success' },
      { name: 'Model selected', status: 'success' },
      { name: 'OCR completed', status: 'success' },
      { name: 'RAG retrieval', status: 'running' },
      { name: 'SOP evidence found', status: 'pending' },
      { name: 'Analysis', status: 'pending' },
      { name: 'DOCX generated', status: 'pending' },
    ]

    for (const step of workflowSteps) {
      await new Promise(r => setTimeout(r, 500))
      setSteps(prev => [...prev.slice(0, -1), step])
    }

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: 'I found 3 critical findings in the inspection report that require attention. Based on the Maintenance SOP, these findings indicate potential safety concerns that should be addressed before equipment operation.',
      sources: mockSources,
      artifactId: 'art_123',
      artifactFilename: 'approval_note.docx',
    }

    setMessages(prev => [...prev, assistantMessage])
    setIsProcessing(false)
    setExternalCalls(0)
  }

  return (
    <div className="flex gap-6 h-full">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-background-secondary rounded-lg border border-border overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-text-secondary">
              <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
              <p className="text-sm">Start a conversation with Sovereign AI</p>
              <p className="text-xs mt-1">All processing happens locally on your infrastructure</p>
            </div>
          )}

          {messages.map(message => (
            <div key={message.id} className="space-y-2">
              <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[70%] rounded-lg px-4 py-2 ${
                    message.role === 'user'
                      ? 'bg-accent-primary text-white'
                      : 'bg-background-tertiary text-text-primary'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>

              {message.sources && message.sources.length > 0 && (
                <div className="ml-4">
                  <p className="text-xs text-text-secondary mb-1">Sources:</p>
                  <div className="flex gap-2">
                    {message.sources.map((source, i) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-1 bg-background-tertiary rounded border border-border"
                      >
                        {source.document} p.{source.page}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {message.artifactId && (
                <div className="ml-4">
                  <div className="inline-flex items-center gap-2 px-3 py-2 bg-accent-success/10 border border-accent-success/30 rounded-lg">
                    <FileText className="w-4 h-4 text-accent-success" />
                    <span className="text-sm text-accent-success">{message.artifactFilename}</span>
                    <button className="text-xs text-accent-primary hover:underline">Download</button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {isProcessing && (
            <div className="space-y-2">
              <div className="flex justify-start">
                <div className="bg-background-tertiary rounded-lg px-4 py-2">
                  <p className="text-sm text-text-secondary">Processing...</p>
                </div>
              </div>
              {steps.length > 0 && (
                <div className="ml-4 space-y-1">
                  {steps.map((step, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      {step.status === 'success' && (
                        <CheckCircle className="w-3 h-3 text-accent-success" />
                      )}
                      {step.status === 'running' && (
                        <div className="w-3 h-3 border border-accent-primary border-t-transparent rounded-full animate-spin" />
                      )}
                      {step.status === 'pending' && (
                        <div className="w-3 h-3 rounded-full bg-border" />
                      )}
                      <span className={step.status === 'pending' ? 'text-text-secondary' : 'text-text-primary'}>
                        {step.name}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="border-t border-border p-4">
          <div className="flex gap-2">
            <button
              type="button"
              className="p-2 rounded-md hover:bg-background-tertiary text-text-secondary"
            >
              <Upload className="w-5 h-5" />
            </button>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask anything..."
              className="flex-1 bg-background-tertiary border border-border rounded-md px-4 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent-primary"
            />
            <button
              type="submit"
              disabled={!input.trim() || isProcessing}
              className="p-2 rounded-md bg-accent-primary text-white disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent-primary/90"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>

      {/* Execution Trace Sidebar */}
      <div className="w-72 bg-background-secondary rounded-lg border border-border p-4 overflow-auto">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Execution Trace</h3>

        {steps.length === 0 && (
          <p className="text-xs text-text-secondary">No execution yet</p>
        )}

        {steps.length > 0 && (
          <div className="space-y-2">
            {steps.map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {step.status === 'success' && (
                  <CheckCircle className="w-3 h-3 text-accent-success" />
                )}
                {step.status === 'running' && (
                  <div className="w-3 h-3 border border-accent-primary border-t-transparent rounded-full animate-spin" />
                )}
                <span className={step.status === 'pending' ? 'text-text-secondary' : 'text-text-primary'}>
                  {step.name}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-border">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-secondary">External calls:</span>
            <span className={`font-mono font-bold ${externalCalls === 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
              {externalCalls}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
