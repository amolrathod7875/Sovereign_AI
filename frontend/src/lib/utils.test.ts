import { describe, it, expect } from 'vitest'
import { modelDisplayName, statusTone, formatBytes, formatDuration, cn } from '../lib/utils'

describe('modelDisplayName', () => {
  it('maps known ids to friendly local model names', () => {
    expect(modelDisplayName('vision')).toBe('Qwen2.5-VL-3B-Instruct')
    expect(modelDisplayName('qwen-coder')).toBe('Qwen2.5-Coder-3B-Instruct')
    expect(modelDisplayName('general')).toBe('Qwen2.5-3B-Instruct')
  })
  it('falls back to the raw id when unknown', () => {
    expect(modelDisplayName('unknown')).toBe('unknown')
    expect(modelDisplayName(null)).toBe('—')
  })
})

describe('statusTone', () => {
  it('returns success tone for ONLINE', () => {
    expect(statusTone('ONLINE').label).toBe('ONLINE')
    expect(statusTone('ONLINE').text).toContain('accent-success')
  })
  it('returns danger tone for UNAVAILABLE', () => {
    expect(statusTone('UNAVAILABLE').text).toContain('accent-danger')
  })
  it('does not invent a healthy status for NOT CONFIGURED', () => {
    expect(statusTone('NOT CONFIGURED').label).toBe('NOT CONFIGURED')
  })
})

describe('formatters', () => {
  it('formats bytes', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1048576)).toBe('1.0 MB')
  })
  it('formats duration', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(500)).toBe('500 ms')
    expect(formatDuration(1500)).toBe('1.5 s')
  })
  it('cn merges class names', () => {
    expect(cn('a', undefined, 'c')).toBe('a c')
  })
})
