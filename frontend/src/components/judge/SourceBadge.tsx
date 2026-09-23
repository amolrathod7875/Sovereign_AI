import type { JudgeSourceType } from '../../lib/api/types'

const SOURCE_LABEL: Record<JudgeSourceType, string> = {
  LIVE: 'LIVE',
  LIVE_PERSISTENT: 'LIVE PERSISTENT',
  COMMITTED_HISTORICAL_EVIDENCE: 'HISTORICAL PROOF',
  FROZEN_EVALUATION_SNAPSHOT: 'FROZEN EVALUATION',
  UNAVAILABLE: 'UNAVAILABLE',
}

const SOURCE_TONE: Record<JudgeSourceType, string> = {
  LIVE: 'bg-accent-primary text-accent-primary',
  LIVE_PERSISTENT: 'bg-accent-success text-accent-success',
  COMMITTED_HISTORICAL_EVIDENCE: 'bg-accent-warning text-accent-warning',
  FROZEN_EVALUATION_SNAPSHOT: 'bg-text-secondary text-text-secondary',
  UNAVAILABLE: 'bg-accent-danger text-accent-danger',
}

interface SourceBadgeProps {
  source_type: JudgeSourceType
  className?: string
}

export default function SourceBadge({ source_type, className }: SourceBadgeProps) {
  const label = SOURCE_LABEL[source_type] ?? source_type
  const tone = SOURCE_TONE[source_type] ?? 'bg-text-secondary text-text-secondary'
  return (
    <span className={['inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide', tone, className].join(' ')}>
      {label}
    </span>
  )
}
