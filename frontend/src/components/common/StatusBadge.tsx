import { cn, statusTone, type ComponentState } from '../../lib/utils'

interface StatusBadgeProps {
  status: ComponentState
  label?: string
  showDot?: boolean
  className?: string
}

export function StatusBadge({ status, label, showDot = true, className }: StatusBadgeProps) {
  const tone = statusTone(status)
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium', tone.text, className)}>
      {showDot && <span className={cn('w-2 h-2 rounded-full', tone.dot)} />}
      {label ?? tone.label}
    </span>
  )
}

export default StatusBadge
