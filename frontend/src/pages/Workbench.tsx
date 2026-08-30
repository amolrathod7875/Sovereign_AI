import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Send,
  Paperclip,
  FileText,
  AlertTriangle,
  Cpu,
  Eye,
  Database,
  Wrench,
  Shield,
  X,
  Image as ImageIcon,
} from 'lucide-react'
import clsx from 'clsx'
import { apiClient, ApiError } from '../lib/api/client'
import { modelDisplayName, cn } from '../lib/utils'
import type {
  AgentRunResponse,
  CoderRunResponse,
  VisionAnalyzeResponse,
  RoutingDecision,
} from '../lib/api/types'

type TaskMode = 'auto' | 'coding' | 'vision' | 'knowledge'

interface ExecutionMeta {
  task: string
  model: string
  rag: boolean | null
  tools: string | null
  local: boolean
  externalCalls: number
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode?: TaskMode
  execution?: ExecutionMeta
  evidence?: Array<{ claim: string | null; source: string | null; document_type: string | null; confidence: number | null }>
  visionResult?: VisionAnalyzeResponse['result'] | null
  visionTags?: string[]
  coderFiles?: Record<string, string>
  coderTest?: CoderRunResponse['test_output']
  artifacts?: Array<{ id: string; name: string; kind: string }>
  externalCalls?: number
  error?: string
}

const VISION_TYPES = ['pid', 'general', 'document', 'ocr', 'inspection']

function resolveArtifacts(names: string[]) {
  if (!names.length) return Promise.resolve<ChatMessage['artifacts']>([])
  return apiClient.listArtifacts().then((infos) => {
    const byName = new Map(infos.map((i) => [i.filename.toLowerCase(), i]))
    const out: NonNullable<ChatMessage['artifacts']> = []
    for (const n of names) {
      const base = n.split(/[\\/]/).pop() || n
      const info = byName.get(base.toLowerCase())
      if (info) {
        out.push({ id: info.artifact_id, name: info.filename, kind: info.kind })
      } else {
        out.push({ id: '', name: base, kind: base.split('.').pop()?.toUpperCase() || 'FILE' })
      }
    }
    return out
  })
}

export default function Workbench() {
  const [input, setInput] = useState('')
  const [mode, setMode] = useState<TaskMode>('auto')
  const [assetTag, setAssetTag] = useState('R-1001')
  const [visionType, setVisionType] = useState('pid')
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, isProcessing])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  function attachFile(f: File | null) {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (!f) {
      setFile(null)
      setPreviewUrl(null)
      return
    }
    setFile(f)
    if (/^image\//.test(f.type)) setPreviewUrl(URL.createObjectURL(f))
    else setPreviewUrl(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if ((!input.trim() && !file) || isProcessing) return

    setError(null)
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: input.trim() || (file ? `[attached: ${file.name}]` : ''),
      mode,
    }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setIsProcessing(true)

    const effectiveMode: TaskMode =
      mode === 'auto' ? (file ? 'vision' : 'knowledge') : mode

    try {
      let assistant: ChatMessage
      if (effectiveMode === 'coding') {
        assistant = await runCoding(input.trim())
      } else if (effectiveMode === 'vision') {
        assistant = await runVision()
      } else {
        // In Auto mode, route text tasks so a coding prompt actually reaches the
        // local coder rather than the maintenance agent.
        if (mode === 'auto' && !file) {
          const d = await apiClient.routeTask({ task: input.trim() })
          if (d.selected_model === 'qwen-coder') {
            assistant = await runCoding(input.trim())
          } else {
            assistant = await runAgentTask(input.trim())
          }
        } else {
          assistant = await runAgentTask(input.trim())
        }
      }
      setMessages((m) => [...m, assistant])
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : 'Request failed'
      setError(detail)
      setMessages((m) => [
        ...m,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          content: `Request failed (${err instanceof ApiError ? err.status : '—'}).`,
          error: detail,
        },
      ])
    } finally {
      setIsProcessing(false)
      attachFile(null)
    }
  }

  async function runCoding(task: string): Promise<ChatMessage> {
    const res = await apiClient.runCoder(task)
    const routing: RoutingDecision | null = res.routing
    const artifacts = await resolveArtifacts(res.files)
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content:
        res.status === 'success' || res.status === 'COMPLETED'
          ? `Coding task completed on the local Qwen Coder model${
              res.test_output?.passed ? ' and the generated code passed its sandbox test.' : '.'
            }`
          : `Coding task finished with status "${res.status}".`,
      mode: 'coding',
      execution: {
        task: 'Coding',
        model: modelDisplayName(routing?.selected_model ?? 'qwen-coder'),
        rag: false,
        tools: 'Sandbox',
        local: routing?.all_local ?? true,
        externalCalls: res.external_calls,
      },
      coderFiles: res.file_contents,
      coderTest: res.test_output,
      artifacts,
      externalCalls: res.external_calls,
    }
  }

  async function runVision(): Promise<ChatMessage> {
    if (!file) throw new ApiError(400, 'Attach an image or PDF for vision analysis.')
    const up = await apiClient.uploadDocument(file)
    const res: VisionAnalyzeResponse = await apiClient.analyzeVision({
      file_path: up.stored_path as string,
      analysis_type: visionType,
      prompt: input.trim() || null,
    })
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: res.result?.description || 'Vision analysis complete.',
      mode: 'vision',
      execution: {
        task: visionType === 'pid' ? 'Vision Analysis (P&ID)' : 'Vision Analysis',
        model: res.model,
        rag: false,
        tools: null,
        local: true,
        externalCalls: res.external_calls,
      },
      visionResult: res.result,
      visionTags: res.equipment_tags,
      externalCalls: res.external_calls,
    }
  }

  async function runAgentTask(task: string): Promise<ChatMessage> {
    const hasImage = !!file
    // If an image is attached, upload it first and hand the LOCAL path to the
    // agent (the browser never sends the bytes anywhere but the local backend).
    let imagePath: string | null = null
    let analysisType = 'general'
    if (hasImage && file) {
      const up = await apiClient.uploadDocument(file)
      imagePath = up.stored_path as string
      analysisType = visionType
    }
    const finalRes: AgentRunResponse = await apiClient.runAgent({
      task,
      asset_tag: assetTag,
      image_path: imagePath,
      analysis_type: analysisType,
    })
    const routing = finalRes.routing
    const artifacts = await resolveArtifacts(finalRes.artifacts as string[])
    const taskLabel = routing?.task_type
      ? routing.task_type
          .replace(/_/g, ' ')
          .toLowerCase()
          .replace(/\b\w/g, (c) => c.toUpperCase())
      : hasImage
        ? 'Multimodal Analysis'
        : 'Knowledge'
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: finalRes.reasoning_summary || finalRes.decision || 'Task complete.',
      mode: hasImage ? 'vision' : 'knowledge',
      execution: {
        task: taskLabel,
        model: modelDisplayName(routing?.selected_model),
        rag: routing?.requires_rag ?? null,
        tools: routing?.requires_tools ? 'Local tools' : null,
        local: routing?.all_local ?? true,
        externalCalls: finalRes.external_calls,
      },
      evidence: finalRes.evidence,
      visionResult: finalRes.vision_evidence?.[0] ?? null,
      visionTags: finalRes.vision_tags,
      artifacts,
      externalCalls: finalRes.external_calls,
    }
  }

  return (
    <div className="flex gap-6 h-full">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-background-secondary rounded-lg border border-border overflow-hidden">
        <div className="border-b border-border p-3 flex flex-wrap items-center gap-2">
          <ModeButton active={mode === 'auto'} onClick={() => setMode('auto')} label="Auto" />
          <ModeButton active={mode === 'coding'} onClick={() => setMode('coding')} label="Coding" icon={Cpu} />
          <ModeButton active={mode === 'vision'} onClick={() => setMode('vision')} label="Vision" icon={Eye} />
          <ModeButton active={mode === 'knowledge'} onClick={() => setMode('knowledge')} label="Knowledge" icon={Database} />
          {mode === 'knowledge' && (
            <input
              aria-label="Asset tag"
              value={assetTag}
              onChange={(e) => setAssetTag(e.target.value)}
              placeholder="Asset tag"
              className="ml-2 bg-background-tertiary border border-border rounded px-2 py-1 text-xs w-28 text-text-primary"
            />
          )}
          {mode === 'vision' && (
            <select
              aria-label="Vision analysis type"
              value={visionType}
              onChange={(e) => setVisionType(e.target.value)}
              className="ml-2 bg-background-tertiary border border-border rounded px-2 py-1 text-xs text-text-primary"
            >
              {VISION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          )}
        </div>

        <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-4">
          {messages.length === 0 && !isProcessing && (
            <div className="flex flex-col items-center justify-center h-full text-text-secondary">
              <Shield className="w-12 h-12 mb-4 opacity-50 text-accent-sovereign" />
              <p className="text-sm">Start a task with Sovereign AI</p>
              <p className="text-xs mt-1">Every step runs on local models — no external calls.</p>
            </div>
          )}

          {messages.map((m) => (
            <MessageView key={m.id} message={m} />
          ))}

          {isProcessing && (
            <div className="flex justify-start">
              <div className="bg-background-tertiary rounded-lg px-4 py-2">
                <p className="text-sm text-text-secondary flex items-center gap-2">
                  <span className="w-3 h-3 border border-accent-primary border-t-transparent rounded-full animate-spin" />
                  Processing on local models…
                </p>
              </div>
            </div>
          )}
          {error && (
            <div className="text-xs text-accent-danger bg-accent-danger/10 border border-accent-danger/30 rounded p-2">
              {error}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-border p-4">
          {file && (
            <div className="mb-2 flex items-center gap-2 text-xs text-text-secondary bg-background-tertiary rounded px-2 py-1 w-fit">
              {previewUrl ? <ImageIcon className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
              <span className="max-w-[240px] truncate">{file.name}</span>
              <button type="button" onClick={() => attachFile(null)} aria-label="Remove attachment">
                <X className="w-3 h-3 hover:text-text-primary" />
              </button>
            </div>
          )}
          <div className="flex gap-2">
            <label className="p-2 rounded-md hover:bg-background-tertiary text-text-secondary cursor-pointer" title="Attach document or image">
              <Paperclip className="w-5 h-5" />
              <input
                type="file"
                className="hidden"
                onChange={(e) => attachFile(e.target.files?.[0] ?? null)}
                accept=".pdf,.docx,.xlsx,.csv,.json,.eml,.jpg,.jpeg,.png,.bmp,.gif,.webp,.tif,.tiff"
              />
            </label>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={file ? 'Optional prompt for the attached file…' : 'Describe the task (coding, P&ID, knowledge)…'}
              aria-label="Task prompt"
              className="flex-1 bg-background-tertiary border border-border rounded-md px-4 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent-primary"
            />
            <button
              type="submit"
              disabled={(!input.trim() && !file) || isProcessing}
              className="p-2 rounded-md bg-accent-primary text-white disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent-primary/90"
              aria-label="Submit task"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>

      {/* Execution + Evidence Panel */}
      <div className="w-80 bg-background-secondary rounded-lg border border-border p-4 overflow-auto">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Execution</h3>
        {messages.filter((m) => m.execution).length === 0 ? (
          <p className="text-xs text-text-secondary">No execution yet.</p>
        ) : (
          <div className="space-y-4">
            {messages
              .filter((m) => m.execution)
              .map((m) => (
                <ExecutionCard key={m.id} message={m} />
              ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ModeButton({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean
  onClick: () => void
  label: string
  icon?: typeof Cpu
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1 px-3 py-1.5 rounded-md text-xs transition-colors',
        active ? 'bg-accent-primary/15 text-accent-primary' : 'text-text-secondary hover:bg-background-tertiary',
      )}
    >
      {Icon && <Icon className="w-3.5 h-3.5" />}
      {label}
    </button>
  )
}

function MessageView({ message }: { message: ChatMessage }) {
  return (
    <div className="space-y-2">
      <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
        <div
          className={clsx(
            'max-w-[80%] rounded-lg px-4 py-2',
            message.role === 'user' ? 'bg-accent-primary text-white' : 'bg-background-tertiary text-text-primary',
          )}
        >
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          {message.error && <p className="text-xs text-accent-danger mt-1">{message.error}</p>}
        </div>
      </div>

      {message.visionResult && (
        <VisionResult result={message.visionResult} tags={message.visionTags} />
      )}

      {message.evidence && message.evidence.length > 0 && <EvidenceList evidence={message.evidence} />}

      {message.coderFiles && Object.keys(message.coderFiles).length > 0 && (
        <CoderFiles files={message.coderFiles} test={message.coderTest} />
      )}

      {message.artifacts && message.artifacts.length > 0 && (
        <div className="ml-4 space-y-1">
          <p className="text-xs text-text-secondary">Artifacts:</p>
          {message.artifacts.map((a) => (
            <ArtifactRow key={a.id || a.name} artifact={a} />
          ))}
        </div>
      )}

      {message.execution && (
        <div className="ml-4 flex items-center gap-2 text-xs">
          <span className="text-text-secondary">External calls:</span>
          <span className={cn('font-mono font-bold', message.execution.externalCalls === 0 ? 'text-accent-success' : 'text-accent-danger')}>
            {message.execution.externalCalls}
          </span>
        </div>
      )}
    </div>
  )
}

function ExecutionCard({ message }: { message: ChatMessage }) {
  const ex = message.execution!
  return (
    <div className="rounded-lg border border-border bg-background-tertiary p-3 space-y-1.5">
      <Row icon={Cpu} label="Task" value={ex.task} />
      <Row icon={Shield} label="Model" value={ex.model} />
      <Row icon={Database} label="RAG" value={ex.rag == null ? '—' : ex.rag ? 'Enabled' : 'Not used'} />
      <Row icon={Wrench} label="Tools" value={ex.tools ?? '—'} />
      <Row
        icon={Shield}
        label="Local"
        value={ex.local ? 'YES' : 'NO'}
        valueClass={ex.local ? 'text-accent-success' : 'text-accent-danger'}
      />
      <Row
        icon={Shield}
        label="External calls"
        value={String(ex.externalCalls)}
        valueClass={ex.externalCalls === 0 ? 'text-accent-success' : 'text-accent-danger'}
      />
    </div>
  )
}

function Row({
  icon: Icon,
  label,
  value,
  valueClass,
}: {
  icon: typeof Cpu
  label: string
  value: string
  valueClass?: string
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="flex items-center gap-1.5 text-text-secondary">
        <Icon className="w-3 h-3" />
        {label}
      </span>
      <span className={cn('font-medium text-text-primary', valueClass)}>{value}</span>
    </div>
  )
}

function VisionResult({
  result,
  tags,
}: {
  result: VisionAnalyzeResponse['result']
  tags?: string[]
}) {
  const findings = (result?.findings as string[] | undefined) ?? []
  const entities = (result?.entities as Array<{ type?: string; name?: string }> | undefined) ?? []
  return (
    <div className="ml-4 rounded-lg border border-border bg-background-tertiary p-3">
      <p className="text-xs font-semibold text-text-primary mb-1">VISUAL ANALYSIS</p>
      <p className="text-xs text-text-secondary mb-2">{result?.description}</p>
      {findings.length > 0 && (
        <ul className="list-disc pl-4 text-xs text-text-primary space-y-0.5">
          {findings.slice(0, 8).map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
      {tags && tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {tags.map((t) => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary">
              {t}
            </span>
          ))}
        </div>
      )}
      {entities.length > 0 && (
        <div className="mt-1 text-[10px] text-text-secondary">
          Entities: {entities.map((e) => e.name).slice(0, 8).join(', ')}
        </div>
      )}
    </div>
  )
}

function EvidenceList({
  evidence,
}: {
  evidence: Array<{ claim: string | null; source: string | null; document_type: string | null; confidence: number | null }>
}) {
  return (
    <div className="ml-4 rounded-lg border border-border bg-background-tertiary p-3">
      <p className="text-xs font-semibold text-text-primary mb-1">KNOWLEDGE RETRIEVAL</p>
      <p className="text-[10px] text-text-secondary mb-2">RAG: Enabled</p>
      <div className="space-y-1.5">
        {evidence.map((e, i) => (
          <div key={i} className="text-xs">
            <p className="text-text-primary">{e.claim || '(no claim)'}</p>
            <p className="text-[10px] text-text-secondary">
              {e.source || 'unknown source'}
              {e.document_type ? ` · ${e.document_type}` : ''}
              {e.confidence != null ? ` · conf ${(e.confidence * 100).toFixed(0)}%` : ''}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

function CoderFiles({ files, test }: { files: Record<string, string>; test?: CoderRunResponse['test_output'] }) {
  return (
    <div className="ml-4 rounded-lg border border-border bg-background-tertiary p-3">
      <p className="text-xs font-semibold text-text-primary mb-1">GENERATED CODE</p>
      {Object.entries(files).map(([name, content]) => (
        <div key={name} className="mb-2">
          <p className="text-[10px] text-text-secondary">{name}</p>
          <pre className="text-[10px] bg-background-primary rounded p-2 overflow-auto max-h-40 text-text-primary whitespace-pre-wrap">
            {content.slice(0, 2000)}
          </pre>
        </div>
      ))}
      {test && (
        <p className={cn('text-[10px]', test.passed ? 'text-accent-success' : 'text-accent-warning')}>
          Sandbox: {test.passed ? 'passed' : 'did not pass'}
          {test.external_network_calls != null ? ` · external calls ${test.external_network_calls}` : ''}
        </p>
      )}
    </div>
  )
}

function ArtifactRow({ artifact }: { artifact: { id: string; name: string; kind: string } }) {
  if (artifact.id) {
    return (
      <a
        href={apiClient.artifactDownloadUrl(artifact.id)}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent-success/10 border border-accent-success/30 rounded-lg text-xs text-accent-success hover:underline"
      >
        <FileText className="w-3.5 h-3.5" />
        {artifact.name}
        <span className="text-[10px] opacity-70">{artifact.kind}</span>
        <Download />
      </a>
    )
  }
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-background-primary border border-border rounded-lg text-xs text-text-secondary">
      <FileText className="w-3.5 h-3.5" />
      {artifact.name}
      <AlertTriangle className="w-3 h-3" />
    </div>
  )
}

function Download() {
  return <span className="text-[10px] underline">Download</span>
}
