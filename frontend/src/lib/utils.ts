import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { VisionAnalyzeResponse } from './api/types'

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

/**
 * Decide whether a vision analysis result must be disclosed as UNAVAILABLE.
 *
 * Pure presentation-layer helper only — it never changes the backend contract.
 * The backend returns a non-null `vision_evidence[0]` even on failure
 * (`confidence: 0`, `uncertain_items: ["vision_error: …"]`) plus a top-level
 * `errors` entry, so a naive "result exists" check would falsely imply success
 * under a top-level VERIFIED. This centralizes the honest disclosure rule.
 */
export function isVisionUnavailable(
  result: VisionAnalyzeResponse['result'] | null | undefined,
  errors?: unknown[],
): { unavailable: boolean; reason: string | null } {
  if (!result) {
    return { unavailable: true, reason: 'No visual analysis result was returned.' }
  }
  const uncertainItems = (result.uncertain_items as string[] | undefined) ?? []
  const visionErrorItem = uncertainItems.find((u) => /vision_error/i.test(String(u))) ?? null
  const errorList = (errors ?? []).map(String)
  const visionErrorFromErrors = errorList.find((e) => /vision/i.test(e)) ?? null
  const confidence = result.confidence ?? null

  const unavailable =
    confidence === 0 || visionErrorItem !== null || visionErrorFromErrors !== null

  if (!unavailable) {
    return { unavailable: false, reason: null }
  }

  const reason = visionErrorItem ?? visionErrorFromErrors ?? 'Visual analysis could not be completed.'
  return { unavailable: true, reason }
}
