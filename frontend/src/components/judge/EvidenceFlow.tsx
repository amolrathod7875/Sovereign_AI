import type { JudgeRunDetail } from '../../lib/api/types'
import { cn } from '../../lib/utils'

interface EvidenceFlowProps {
  run: JudgeRunDetail
}

const NODES = [
  { key: 'asset', label: 'ASSET', getValue: (r: JudgeRunDetail) => r.asset.identity_status ?? '—' },
  { key: 'retrieval', label: 'RETRIEVAL', getValue: (r: JudgeRunDetail) => `${r.retrieval.chunk_count ?? 0} chunks` },
  { key: 'tools', label: 'TOOLS', getValue: (r: JudgeRunDetail) => r.calculations.sandbox_used ? 'Sandbox used' : 'Not recorded' },
  { key: 'human', label: 'HUMAN', getValue: (r: JudgeRunDetail) => r.human_review.status },
  { key: 'receipt', label: 'RECEIPT', getValue: (r: JudgeRunDetail) => r.receipt.available ? (r.receipt.valid ? 'Valid' : 'Invalid') : 'Not available' },
  { key: 'chain', label: 'CHAIN', getValue: (r: JudgeRunDetail) => r.chain.linked ? `#${r.chain.sequence_no ?? '?'} ${r.chain.global_chain_status}` : 'Not linked' },
] as const

export default function EvidenceFlow({ run }: EvidenceFlowProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {NODES.map((node, idx) => {
        const value = node.getValue(run)
        const isReceipt = node.key === 'receipt'
        const isChain = node.key === 'chain'
        let tone: 'default' | 'success' | 'warning' | 'danger' = 'default'
        if (isReceipt && run.receipt.available) tone = run.receipt.valid ? 'success' : 'danger'
        else if (isChain && run.chain.linked) tone = run.chain.global_chain_valid ? 'success' : 'danger'
        else if (node.key === 'human' && run.human_review.status === 'PENDING') tone = 'warning'
        else if (node.key === 'human' && (run.human_review.status === 'APPROVED' || run.human_review.status === 'REJECTED')) tone = 'success'

        return (
          <div key={node.key} className="flex items-center gap-1">
            <div
              className={cn(
                'flex flex-col items-center gap-1 px-3 py-2 rounded-md border min-w-[90px]',
                tone === 'success' && 'border-accent-success/40 bg-accent-success/5',
                tone === 'warning' && 'border-accent-warning/40 bg-accent-warning/5',
                tone === 'danger' && 'border-accent-danger/40 bg-accent-danger/5',
                tone === 'default' && 'border-border bg-background-tertiary',
              )}
            >
              <span className="text-[10px] font-semibold text-text-secondary uppercase tracking-wide">{node.label}</span>
              <span className={cn('text-xs font-medium', tone === 'success' && 'text-accent-success', tone === 'danger' && 'text-accent-danger', tone === 'warning' && 'text-accent-warning', tone === 'default' && 'text-text-primary')}>
                {value}
              </span>
            </div>
            {idx < NODES.length - 1 && <div className="text-text-secondary text-xs">→</div>}
          </div>
        )
      })}
    </div>
  )
}
