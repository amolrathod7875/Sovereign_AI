import { useState, type FormEvent } from 'react'

interface HashValueProps {
  value: string | null | undefined
  label: string
  className?: string
}

export default function HashValue({ value, label, className }: HashValueProps) {
  const [copied, setCopied] = useState(false)
  const display = typeof value === 'string' && value.length > 12 ? `${value.slice(0, 12)}…${value.slice(-4)}` : value ?? '—'

  async function copyHash(e: FormEvent) {
    e.preventDefault()
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      // clipboard unavailable — silent fail for read-only UI
    }
  }

  return (
    <div className={['flex items-center gap-2', className].join(' ')}>
      <span className="text-[10px] font-medium text-text-secondary uppercase tracking-wide">{label}</span>
      <code className="flex-1 font-mono text-xs text-text-primary bg-background-tertiary rounded px-2 py-1 break-all">{display}</code>
      {typeof value === 'string' && value.length > 0 && (
        <form onSubmit={copyHash}>
          <button
            type="submit"
            aria-label={`Copy ${label} hash`}
            className="text-[10px] px-2 py-1 rounded border border-border text-text-secondary hover:text-text-primary hover:bg-background-tertiary transition-colors"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </form>
      )}
    </div>
  )
}
