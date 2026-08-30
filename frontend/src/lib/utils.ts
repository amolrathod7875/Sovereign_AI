import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/**
 * Map a backend model id to a human-friendly display name.
 *
 * The backend `RoutingDecision.selected_model` is an id (`vision`, `qwen-coder`,
 * `general`); the authoritative registry holds the real local weights names. We
 * keep this mapping in the UI only — it is display text, never a routing decision.
 */
const MODEL_DISPLAY: Record<string, string> = {
  vision: 'Qwen2.5-VL-3B-Instruct',
  'qwen-vl': 'Qwen2.5-VL-3B-Instruct',
  'qwen-coder': 'Qwen2.5-Coder-3B-Instruct',
  coder: 'Qwen2.5-Coder-3B-Instruct',
  general: 'Qwen2.5-3B-Instruct',
}

export function modelDisplayName(id: string | null | undefined): string {
  if (!id) return '—'
  return MODEL_DISPLAY[id] ?? id
}

/** Honest status vocabulary shared with backend/app/api/system.py. */
export type ComponentState = 'ONLINE' | 'OFFLINE' | 'UNAVAILABLE' | 'NOT CONFIGURED' | string

export function statusTone(status: ComponentState): {
  dot: string
  text: string
  label: string
} {
  switch (status) {
    case 'ONLINE':
      return { dot: 'bg-accent-success', text: 'text-accent-success', label: 'ONLINE' }
    case 'OFFLINE':
      return { dot: 'bg-accent-warning', text: 'text-accent-warning', label: 'OFFLINE' }
    case 'UNAVAILABLE':
      return { dot: 'bg-accent-danger', text: 'text-accent-danger', label: 'UNAVAILABLE' }
    case 'NOT CONFIGURED':
      return { dot: 'bg-text-secondary', text: 'text-text-secondary', label: 'NOT CONFIGURED' }
    default:
      return { dot: 'bg-text-secondary', text: 'text-text-secondary', label: String(status) }
  }
}

export function formatBytes(bytes: number): string {
  if (!bytes && bytes !== 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}
