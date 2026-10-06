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
  Clock,
  Gauge,
  Plus,
  Trash2,
  Pencil,
} from 'lucide-react'
import clsx from 'clsx'
import { apiClient, ApiError } from '../lib/api/client'
import { modelDisplayName, cn, isVisionUnavailable } from '../lib/utils'
import type {
  AgentRunResponse,
  CoderRunResponse,
  VisionAnalyzeResponse,
  RoutingDecision,
  ModelPerformanceMetrics,
  ConversationSummary,
  ConversationMessage,
  CreateUserMessageRequest,
} from '../lib/api/types'

type TaskMode = 'auto' | 'coding' | 'vision' | 'knowledge'

interface ExecutionMeta {
  task: string
  routing: string | null
  actualModel: string
  rag: boolean | null | string
  tools: string | null
  local: boolean
  externalCalls: number
  responseTimeSeconds: number | null
  tokensPerSecond: number | null
  promptTokens: number | null
  completionTokens: number | null
  totalTokens: number | null
  modelInferenceSeconds: number | null
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
  errors?: unknown[]
  coderFiles?: Record<string, string>
  coderTest?: CoderRunResponse['test_output']
  artifacts?: Array<{ id: string; name: string; kind: string }>
  externalCalls?: number
  error?: string
  modelPerformance?: ModelPerformanceMetrics | null
  memoryContext?: { used: boolean; included_count: number; scopes: string[] } | null
}

const VISION_TYPES = ['pid', 'general', 'document', 'ocr', 'inspection']

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  if (seconds < 60) return `${seconds.toFixed(2)} s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function formatTokens(m: ModelPerformanceMetrics | null | undefined): string | null {
  if (!m) return null
  const parts: string[] = []
  if (m.prompt_tokens != null) parts.push(`${m.prompt_tokens} in`)
  if (m.completion_tokens != null) parts.push(`${m.completion_tokens} out`)
  return parts.length ? parts.join(' / ') : null
}

function isIndustrialWorkflowRequest(task: string): boolean {
  const text = task.toLowerCase()
  const hasAsset = /r-1001|asset|equipment|reactor/.test(text)
  const hasEvidence = /operating data|sensor|inspection findings|equipment manual|maintenance sop|vendor recommendation|vendor correspondence|asset profile|threshold|corrective action/.test(text)
  const hasAction = /analyze|assess|determine|prepare|recommend|evaluate|decide|approval|corrective|maintenance decision|workflow/.test(text)
  return hasAsset && (hasEvidence || hasAction)
}

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

function chatMessageToPersistentPayload(msg: ChatMessage, _conversationId: string): CreateUserMessageRequest {
  return {
    client_message_id: msg.id,
    content: msg.content,
    mode: msg.mode ?? null,
    attachments: [],
  }
}

function persistedMessageToChatMessage(msg: ConversationMessage): ChatMessage {
  const payload = msg.display_payload as Record<string, unknown> | null
  const execution = payload?.execution as ExecutionMeta | undefined
  return {
    id: msg.client_message_id || msg.id,
    role: msg.role,
    content: msg.content || '',
    mode: (msg.mode as TaskMode | undefined) ?? execution?.task ? 'knowledge' : undefined,
    execution,
    evidence: (payload?.evidence as ChatMessage['evidence']) ?? [],
    visionResult: (payload?.visionResult as ChatMessage['visionResult']) ?? null,
    visionTags: (payload?.visionTags as ChatMessage['visionTags']) ?? [],
    errors: (payload?.errors as ChatMessage['errors']) ?? [],
    coderFiles: (payload?.coderFiles as ChatMessage['coderFiles']) ?? undefined,
    coderTest: (payload?.coderTest as ChatMessage['coderTest']) ?? undefined,
    artifacts: (payload?.artifacts as ChatMessage['artifacts']) ?? [],
    externalCalls: msg.external_calls ?? execution?.externalCalls,
    error: msg.error_detail ?? undefined,
    modelPerformance: execution
      ? {
          prompt_tokens: msg.prompt_tokens ?? execution.promptTokens ?? null,
          completion_tokens: msg.completion_tokens ?? execution.completionTokens ?? null,
          total_tokens: msg.total_tokens ?? execution.totalTokens ?? null,
          inference_seconds: msg.model_inference_seconds ?? execution.modelInferenceSeconds ?? null,
          tokens_per_second: msg.tokens_per_second ?? execution.tokensPerSecond ?? null,
        }
      : null,
  }
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
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

  // History state
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [_historyMessages, setHistoryMessages] = useState<ConversationMessage[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyUnavailable, setHistoryUnavailable] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [isNewChat, setIsNewChat] = useState(true)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, isProcessing])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  // Load conversation list on mount and when history becomes available
  useEffect(() => {
    if (historyUnavailable) return
    let cancelled = false
    async function loadConversations() {
      try {
        const list = await apiClient.listConversations()
        if (!cancelled) setConversations(list)
      } catch (err) {
        if (!cancelled) {
          const detail = err instanceof ApiError ? err.detail : 'History unavailable'
          if (err instanceof ApiError && err.status === 503) {
            setHistoryUnavailable(true)
          }
          setHistoryError(detail)
        }
      }
    }
    loadConversations()
    return () => {
      cancelled = true
    }
  }, [historyUnavailable])

  // Load conversation from URL parameter
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const cid = params.get('conversation')
    if (cid && !selectedConversationId && !historyUnavailable) {
      openConversation(cid)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openConversation(conversationId: string) {
    setHistoryLoading(true)
    setHistoryError(null)
    setSelectedConversationId(conversationId)
    setIsNewChat(false)
    setMessages([])
    try {
      const msgs = await apiClient.getConversationMessages(conversationId, 500, 0)
      setHistoryMessages(msgs)
      setMessages(msgs.map(persistedMessageToChatMessage))
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : 'Failed to load conversation'
      setHistoryError(detail)
      if (err instanceof ApiError && err.status === 404) {
        setSelectedConversationId(null)
        setIsNewChat(true)
      }
    } finally {
      setHistoryLoading(false)
    }
  }

  async function handleNewChat() {
    setSelectedConversationId(null)
    setIsNewChat(true)
    setMessages([])
    setHistoryMessages([])
    setError(null)
    const url = new URL(window.location.href)
    url.searchParams.delete('conversation')
    window.history.replaceState({}, '', url.toString())
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if ((!input.trim() && !file) || isProcessing) return

    setError(null)

    let _conversationId = selectedConversationId

    // Lazily create conversation on first message
    if (!_conversationId) {
      try {
        const conv = await apiClient.createConversation({ title: 'New conversation' })
        _conversationId = conv.id
        setSelectedConversationId(_conversationId)
        setIsNewChat(false)
        // Update URL
        const url = new URL(window.location.href)
        url.searchParams.set('conversation', _conversationId)
        window.history.replaceState({}, '', url.toString())
        // Refresh conversation list
        const list = await apiClient.listConversations()
        setConversations(list)
      } catch (err) {
        const detail = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : 'Failed to create conversation'
        setError(detail)
        return
      }
    }

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

    let currentMessageId: string | null = null

    // Persist user message BEFORE inference so the context builder can reference it.
    if (_conversationId) {
      try {
        const persistedUser = await apiClient.createConversationMessage(
          _conversationId,
          chatMessageToPersistentPayload(userMsg, _conversationId),
        )
        currentMessageId = persistedUser.id
      } catch (persistErr) {
        console.warn('History persistence failed (session continues):', persistErr)
      }
    }

    try {
      let assistant: ChatMessage
      if (effectiveMode === 'coding') {
        assistant = await runCoding(input.trim())
      } else if (effectiveMode === 'vision') {
        assistant = await runVision()
      } else if (mode === 'knowledge') {
        assistant = await runGeneral(input.trim(), true, currentMessageId)
      } else {
        if (mode === 'auto' && !file) {
          const d = await apiClient.routeTask({ task: input.trim() })
          const taskType = d.task_type || ''
          if (taskType === 'CODING') {
            assistant = await runCoding(input.trim())
          } else if (taskType === 'DOCUMENT_ANALYSIS' && d.selected_model === 'vision') {
            assistant = await runVision()
          } else if (taskType === 'GENERAL_QA') {
            assistant = await runGeneral(input.trim(), false, currentMessageId)
          } else if (taskType === 'RAG_QA') {
            assistant = await runGeneral(input.trim(), true, currentMessageId)
          } else if (isIndustrialWorkflowRequest(input.trim())) {
            assistant = await runAgentTask(input.trim())
          } else {
            assistant = await runGeneral(input.trim(), false, currentMessageId)
          }
        } else {
          assistant = await runAgentTask(input.trim())
        }
      }

      setMessages((m) => [...m, assistant])

      // Refresh trusted history from backend after successful inference.
      if (_conversationId) {
        try {
          const list = await apiClient.listConversations()
          setConversations(list)
          if (selectedConversationId === _conversationId) {
            const msgs = await apiClient.getConversationMessages(_conversationId, 500, 0)
            setHistoryMessages(msgs)
            setMessages(msgs.map(persistedMessageToChatMessage))
          }
        } catch (refreshErr) {
          console.warn('History refresh failed (session continues):', refreshErr)
        }
      }
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

  async function runCoding(task: string): Promise<ChatMessage> {
    const res = await apiClient.runCoder(task)
    const routing: RoutingDecision | null = res.routing
    const artifacts = await resolveArtifacts(res.files)
    const routingModel = modelDisplayName(routing?.selected_model ?? 'qwen-coder')
    const mp = res.model_performance ?? null
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
        routing: routingModel,
        actualModel: routingModel,
        rag: false,
        tools: 'Sandbox',
        local: routing?.all_local ?? true,
        externalCalls: res.external_calls,
        responseTimeSeconds: res.response_time_seconds ?? null,
        tokensPerSecond: mp?.tokens_per_second ?? null,
        promptTokens: mp?.prompt_tokens ?? null,
        completionTokens: mp?.completion_tokens ?? null,
        totalTokens: mp?.total_tokens ?? null,
        modelInferenceSeconds: mp?.inference_seconds ?? null,
      },
      coderFiles: res.file_contents,
      coderTest: res.test_output,
      artifacts,
      externalCalls: res.external_calls,
      modelPerformance: mp,
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
    const mp = res.model_performance ?? null
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: res.result?.description || 'Vision analysis complete.',
      mode: 'vision',
      execution: {
        task: visionType === 'pid' ? 'Vision Analysis (P&ID)' : 'Vision Analysis',
        routing: res.model,
        actualModel: res.model,
        rag: false,
        tools: null,
        local: true,
        externalCalls: res.external_calls,
        responseTimeSeconds: res.response_time_seconds ?? null,
        tokensPerSecond: mp?.tokens_per_second ?? null,
        promptTokens: mp?.prompt_tokens ?? null,
        completionTokens: mp?.completion_tokens ?? null,
        totalTokens: mp?.total_tokens ?? null,
        modelInferenceSeconds: mp?.inference_seconds ?? null,
      },
      visionResult: res.result,
      visionTags: res.equipment_tags,
      externalCalls: res.external_calls,
      modelPerformance: mp,
    }
  }

  async function runGeneral(task: string, useRag = false, currentMessageId?: string | null): Promise<ChatMessage> {
    const res = await apiClient.runGeneral({
      task,
      asset_tag: assetTag,
      use_rag: useRag,
      conversation_id: selectedConversationId,
      current_message_id: currentMessageId ?? null,
    })
    const taskLabel = res.routing?.task_type
      ? String(res.routing.task_type).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
      : 'General'
    const routingModel = (res.routing?.selected_model as string | undefined) || 'general'
    const actualModel = res.actual_model_execution?.length
      ? res.actual_model_execution.join(', ')
      : 'NONE'
    const mp = res.model_performance ?? null
    const memMeta = res.memory_context ?? null
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: res.answer || res.message || 'General task complete.',
      mode: 'knowledge',
      execution: {
        task: taskLabel,
        routing: modelDisplayName(routingModel),
        actualModel,
        rag: res.rag_used ? 'Enabled' : 'Not used',
        tools: null,
        local: res.actual_model_execution.length > 0,
        externalCalls: res.external_calls,
        responseTimeSeconds: res.response_time_seconds ?? null,
        tokensPerSecond: mp?.tokens_per_second ?? null,
        promptTokens: mp?.prompt_tokens ?? null,
        completionTokens: mp?.completion_tokens ?? null,
        totalTokens: mp?.total_tokens ?? null,
        modelInferenceSeconds: mp?.inference_seconds ?? null,
      },
      evidence: res.evidence?.map((e) => ({
        claim: e.claim,
        source: e.source,
        document_type: e.document_type,
        confidence: e.confidence,
      })) || [],
      errors: res.errors,
      externalCalls: res.external_calls,
      modelPerformance: mp,
      memoryContext: memMeta
        ? {
            used: memMeta.used,
            included_count: memMeta.included_count,
            scopes: memMeta.scopes ?? [],
          }
        : null,
    }
  }

  async function runAgentTask(task: string): Promise<ChatMessage> {
    const hasImage = !!file
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
    const routingModel = modelDisplayName(routing?.selected_model)
    const mp = finalRes.model_performance ?? null
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: finalRes.reasoning_summary || finalRes.decision || 'Task complete.',
      mode: hasImage ? 'vision' : 'knowledge',
      execution: {
        task: taskLabel,
        routing: routingModel,
        actualModel: 'Industrial LangGraph workflow',
        rag: routing?.requires_rag ?? null,
        tools: routing?.requires_tools ? 'Local tools' : null,
        local: routing?.all_local ?? true,
        externalCalls: finalRes.external_calls,
        responseTimeSeconds: finalRes.response_time_seconds ?? null,
        tokensPerSecond: mp?.tokens_per_second ?? null,
        promptTokens: mp?.prompt_tokens ?? null,
        completionTokens: mp?.completion_tokens ?? null,
        totalTokens: mp?.total_tokens ?? null,
        modelInferenceSeconds: mp?.inference_seconds ?? null,
      },
      evidence: finalRes.evidence,
      visionResult: finalRes.vision_evidence?.[0] ?? null,
      visionTags: finalRes.vision_tags,
      errors: finalRes.errors,
      artifacts,
      externalCalls: finalRes.external_calls,
      modelPerformance: mp,
    }
  }

  async function handleDeleteConversation(conversationId: string) {
    if (!confirm('Delete this conversation? This cannot be undone.')) return
    try {
      await apiClient.deleteConversation(conversationId)
      if (selectedConversationId === conversationId) {
        handleNewChat()
      }
      const list = await apiClient.listConversations()
      setConversations(list)
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : 'Delete failed'
      setError(detail)
    }
  }

  async function handleRename(conversationId: string) {
    if (!renameValue.trim()) return
    try {
      await apiClient.updateConversation(conversationId, { title: renameValue.trim() })
      setRenamingId(null)
      setRenameValue('')
      const list = await apiClient.listConversations()
      setConversations(list)
      // Update current if same conversation
      if (selectedConversationId === conversationId) {
        await apiClient.getConversation(conversationId)
        // title is shown in conversation list; no local message state change needed
      }
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : err instanceof Error ? err.message : 'Rename failed'
      setError(detail)
    }
  }

  const selectedConversation = conversations.find((c) => c.id === selectedConversationId) || null

  return (
    <div className="flex gap-6 h-full">
      {/* Conversations Panel */}
      <div className="w-64 flex flex-col bg-background-secondary rounded-lg border border-border overflow-hidden">
        <div className="border-b border-border p-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">History</h3>
          <button
            type="button"
            onClick={handleNewChat}
            className="p-1 rounded hover:bg-background-tertiary text-text-secondary hover:text-text-primary"
            title="New Chat"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {historyUnavailable && (
          <div className="p-3 text-xs text-accent-warning bg-accent-warning/10 border-b border-accent-warning/30">
            History unavailable
          </div>
        )}

        <div className="flex-1 overflow-auto">
          {historyLoading && (
            <div className="p-3 text-xs text-text-secondary">Loading…</div>
          )}
          {!historyLoading && conversations.length === 0 && !historyUnavailable && (
            <div className="p-3 text-xs text-text-secondary">No conversations yet.</div>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={clsx(
                'group flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-border/50 hover:bg-background-tertiary',
                selectedConversationId === c.id ? 'bg-accent-primary/10' : '',
              )}
              onClick={() => openConversation(c.id)}
            >
              <div className="flex-1 min-w-0">
                {renamingId === c.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => handleRename(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRename(c.id)
                      if (e.key === 'Escape') setRenamingId(null)
                    }}
                    className="w-full text-xs bg-background-primary border border-border rounded px-1 py-0.5 text-text-primary"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <p className="text-xs text-text-primary truncate">{c.title || 'New conversation'}</p>
                )}
                <p className="text-[10px] text-text-secondary">{timeAgo(c.last_message_at || c.updated_at)}</p>
              </div>
              <div className="hidden group-hover:flex items-center gap-1">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setRenamingId(c.id)
                    setRenameValue(c.title || '')
                  }}
                  className="p-0.5 rounded hover:bg-background-primary text-text-secondary"
                  title="Rename"
                >
                  <Pencil className="w-3 h-3" />
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDeleteConversation(c.id)
                  }}
                  className="p-0.5 rounded hover:bg-background-primary text-accent-danger"
                  title="Delete"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-background-secondary rounded-lg border border-border overflow-hidden">
        <div className="border-b border-border p-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleNewChat}
            className="p-1.5 rounded-md hover:bg-background-tertiary text-text-secondary hover:text-text-primary"
            title="New Chat"
          >
            <Plus className="w-4 h-4" />
          </button>
          {!isNewChat && selectedConversation && (
            <span className="text-xs text-text-secondary truncate max-w-[200px]">
              {selectedConversation.title || 'New conversation'}
            </span>
          )}
          {isNewChat && (
            <span className="text-xs text-text-secondary">New Chat</span>
          )}
          <div className="flex-1" />
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
          {historyLoading && (
            <div className="flex justify-center py-8">
              <div className="text-xs text-text-secondary">Loading conversation…</div>
            </div>
          )}
          {historyError && (
            <div className="text-xs text-accent-warning bg-accent-warning/10 border border-accent-warning/30 rounded p-2">
              {historyError}
            </div>
          )}
          {messages.length === 0 && !isProcessing && !historyLoading && (
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
  const speed = message.modelPerformance?.tokens_per_second != null && message.modelPerformance.tokens_per_second > 0
    ? `${message.modelPerformance.tokens_per_second.toFixed(1)} tok/s`
    : null
  const duration = message.execution?.responseTimeSeconds ?? null
  const metricLine = speed
    ? `${formatDuration(duration)}  \u2022  ${speed}`
    : formatDuration(duration)
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
        <VisionResult result={message.visionResult} tags={message.visionTags} errors={message.errors} />
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

      {message.role === 'assistant' && metricLine && (
        <div className="ml-4 text-[10px] text-text-secondary">
          {metricLine}
        </div>
      )}
    </div>
  )
}

function ExecutionCard({ message }: { message: ChatMessage }) {
  const ex = message.execution!
  const ragText = ex.rag == null
    ? '—'
    : typeof ex.rag === 'string'
      ? ex.rag
      : ex.rag
        ? 'Enabled'
        : 'Not used'
  const speed = ex.tokensPerSecond != null && ex.tokensPerSecond > 0
    ? `${ex.tokensPerSecond.toFixed(1)} tok/s`
    : null
  const tokens = formatTokens(message.modelPerformance)
  const memLabel = message.memoryContext
    ? message.memoryContext.used
      ? `Memory: ${message.memoryContext.included_count} used`
      : 'Memory: none used'
    : null
  return (
    <div className="rounded-lg border border-border bg-background-tertiary p-3 space-y-1.5">
      <Row icon={Clock} label="Response time" value={formatDuration(ex.responseTimeSeconds)} />
      <Row icon={Cpu} label="Task" value={ex.task} />
      <Row icon={Database} label="Routing" value={ex.routing ?? '—'} />
      <Row icon={Cpu} label="Actual execution" value={ex.actualModel} />
      <Row icon={Database} label="RAG" value={ragText} />
      <Row icon={Wrench} label="Tools" value={ex.tools ?? '—'} />
      {memLabel && <Row icon={Database} label={memLabel.startsWith('Memory:') ? 'Memory' : 'Context'} value={memLabel.split(': ')[1] ?? memLabel} />}
      {speed && <Row icon={Gauge} label="Generation" value={speed} />}
      {!speed && ex.responseTimeSeconds != null && (
        <Row icon={Gauge} label="Generation" value="—" />
      )}
      {tokens && <Row icon={Cpu} label="Tokens" value={tokens} />}
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

export function VisionResult({
  result,
  tags,
  errors,
}: {
  result: VisionAnalyzeResponse['result']
  tags?: string[]
  errors?: unknown[]
}) {
  const { unavailable, reason } = isVisionUnavailable(result, errors)

  if (unavailable) {
    return (
      <div className="ml-4 rounded-lg border border-accent-danger/40 bg-accent-danger/10 p-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-accent-danger mb-1">
          <AlertTriangle className="w-3.5 h-3.5" />
          VISION ANALYSIS UNAVAILABLE
        </p>
        {reason && <p className="text-xs text-text-secondary">{reason}</p>}
        <p className="mt-1 text-[10px] text-text-secondary">
          No visual evidence was obtained. Any answer shown is based on knowledge retrieval only and does
          not include visual verification.
        </p>
      </div>
    )
  }

  const findings = (result?.findings as string[] | undefined) ?? []
  const entities = (result?.entities as Array<{ type?: string; name?: string }> | undefined) ?? []
  return (
    <div className="ml-4 rounded-lg border border-border bg-background-tertiary p-3">
      <p className="text-xs font-semibold text-accent-success mb-1">VISUAL ANALYSIS · AVAILABLE</p>
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
  const [downloading, setDownloading] = useState(false)

  async function handleDownload() {
    if (!artifact.id || downloading) return
    setDownloading(true)
    try {
      const { blob } = await apiClient.downloadArtifact(artifact.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = artifact.name
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      // handled by global error state in parent
    } finally {
      setDownloading(false)
    }
  }

  if (artifact.id) {
    return (
      <button
        type="button"
        onClick={handleDownload}
        disabled={downloading}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-accent-success/10 border border-accent-success/30 rounded-lg text-xs text-accent-success hover:underline disabled:opacity-50"
      >
        <FileText className="w-3.5 h-3.5" />
        {artifact.name}
        <span className="text-[10px] opacity-70">{artifact.kind}</span>
        <DownloadLabel />
      </button>
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

function DownloadLabel() {
  return <span className="text-[10px] underline">Download</span>
}
