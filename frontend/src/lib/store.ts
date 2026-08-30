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

function modelAvailability(models: ModelInfo[]): { available: number; total: number } {
  const total = models.filter((m) => m.id !== 'embedding' && m.id !== 'reranker').length || 1
  const available = models.filter(
    (m) => m.id !== 'embedding' && m.id !== 'reranker' && (m.status === 'online' || m.status === 'active'),
  ).length
  return { available, total }
}

export function summarizeModels(models: ModelInfo[]): { available: number; total: number } {
  return modelAvailability(models)
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
