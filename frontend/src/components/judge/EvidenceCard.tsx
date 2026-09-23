import type { ReactNode } from 'react'

interface EvidenceCardProps {
  title: string
  badge?: ReactNode
  children: ReactNode
  className?: string
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info'
}

const TONE_BORDER: Record<string, string> = {
  default: 'border-border',
  success: 'border-accent-success/40',
  warning: 'border-accent-warning/40',
  danger: 'border-accent-danger/40',
  info: 'border-accent-primary/40',
}

export default function EvidenceCard({ title, badge, children, className, tone = 'default' }: EvidenceCardProps) {
  return (
    <div className={['bg-background-secondary rounded-lg border p-4', TONE_BORDER[tone], className].join(' ')}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">{title}</h3>
        {badge}
      </div>
      {children}
    </div>
  )
}
