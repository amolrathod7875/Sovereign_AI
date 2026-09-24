import { create } from 'zustand'
import type { SystemStatus, ModelInfo } from './api/types'
import { getSystemStatus, listModels } from './api/client'
import { ApiError } from './api/client'

interface SystemStore {
  status: SystemStatus | null
  models: ModelInfo[]
  loading: boolean
  error: string | null
  lastUpdated: number | null

  /** Fetch once (used on mount). */
  refresh: () => Promise<void>
  /** Begin polling every `intervalMs`. Returns a stop function. */
  startPolling: (_intervalMs?: number) => () => void
}

function modelAvailability(models: ModelInfo[], components?: Array<{ id: string; status: string }>): { available: number; total: number } {
  const modelIds = new Set(['qwen-coder', 'vision', 'general'])
  if (components && components.length > 0) {
    const total = 3
    const available = components.filter((c) => modelIds.has(c.id) && c.status === 'ONLINE').length
    return { available, total }
  }
  const total = models.filter((m) => m.id !== 'embedding' && m.id !== 'reranker').length || 1
  const available = models.filter(
    (m) => {
      if (m.id === 'embedding' || m.id === 'reranker') return false
      const s = (m.status || '').toLowerCase()
      return s === 'online' || s === 'active'
    },
  ).length
  return { available, total }
}

export function summarizeModels(models: ModelInfo[], components?: Array<{ id: string; status: string }>): { available: number; total: number } {
  return modelAvailability(models, components)
}

export const useSystemStore = create<SystemStore>((set, get) => ({
  status: null,
  models: [],
  loading: false,
  error: null,
  lastUpdated: null,

  refresh: async () => {
    if (get().loading) return
    set({ loading: true })
    try {
      const [status, models] = await Promise.allSettled([getSystemStatus(), listModels()])
      const st = status.status === 'fulfilled' ? status.value : null
      const md = models.status === 'fulfilled' ? models.value : []
      const err =
        status.status === 'rejected'
          ? status.reason instanceof ApiError
            ? status.reason.detail
            : 'Backend unreachable'
          : null
      set({ status: st, models: md, loading: false, error: err, lastUpdated: Date.now() })
    } catch (e) {
      set({
        loading: false,
        error: e instanceof ApiError ? e.detail : 'Failed to load system status',
        lastUpdated: Date.now(),
      })
    }
  },

  startPolling: (intervalMs = 15000) => {
    // Immediate first load.
    void get().refresh()
    const id = window.setInterval(() => {
      void get().refresh()
    }, intervalMs)
    return () => window.clearInterval(id)
  },
}))
