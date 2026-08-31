import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isVisionUnavailable } from '../lib/utils'
import { VisionResult } from '../pages/Workbench'
import type { VisionEvidence } from '../lib/api/types'

const successResult: VisionEvidence = {
  description: 'A P&ID shows a pump and a valve.',
  findings: ['Pump P-101 present', 'Valve V-202 present'],
  entities: [{ type: 'equipment', name: 'P-101' }],
  uncertain_items: [],
  confidence: 0.85,
  model: 'Qwen2.5-VL-3B-Instruct',
  data_origin: 'local',
}

const failedResult: VisionEvidence = {
  description: '',
  findings: [],
  entities: [],
  uncertain_items: ['vision_error: Connection error.'],
  confidence: 0.0,
  model: 'Qwen2.5-VL-3B-Instruct',
  data_origin: 'local',
}

const zeroConfidenceResult: VisionEvidence = {
  description: 'Ambiguous image.',
  findings: [],
  entities: [],
  uncertain_items: ['item (uncertain)'],
  confidence: 0.0,
  model: 'Qwen2.5-VL-3B-Instruct',
  data_origin: 'local',
}

describe('isVisionUnavailable — detection logic', () => {
  it('vision success is available', () => {
    const { unavailable, reason } = isVisionUnavailable(successResult)
    expect(unavailable).toBe(false)
    expect(reason).toBeNull()
  })

  it('vision unavailable when result is null', () => {
    const { unavailable } = isVisionUnavailable(null)
    expect(unavailable).toBe(true)
  })

  it('vision error in uncertain_items is detected', () => {
    const { unavailable, reason } = isVisionUnavailable(failedResult)
    expect(unavailable).toBe(true)
    expect(reason).toContain('Connection error.')
  })

  it('zero-confidence vision is detected', () => {
    const { unavailable } = isVisionUnavailable(zeroConfidenceResult)
    expect(unavailable).toBe(true)
  })

  it('vision error surfaced via top-level errors array', () => {
    const { unavailable, reason } = isVisionUnavailable(successResult, ['vision:Connection error.'])
    expect(unavailable).toBe(true)
    expect(reason).toContain('Connection error.')
  })

  it('non-vision errors do not mask a successful vision result', () => {
    const { unavailable } = isVisionUnavailable(successResult, ['retrieve:pdf:fail'])
    expect(unavailable).toBe(false)
  })
})

describe('VisionResult — disclosure UI', () => {
  it('vision success renders AVAILABLE without a warning', () => {
    render(<VisionResult result={successResult} tags={['P-101']} />)
    expect(screen.getByText(/VISUAL ANALYSIS/i)).toBeInTheDocument()
    expect(screen.getByText(/VISUAL ANALYSIS · AVAILABLE/i)).toBeInTheDocument()
    expect(screen.queryByText(/VISION ANALYSIS UNAVAILABLE/i)).not.toBeInTheDocument()
    expect(screen.getByText('A P&ID shows a pump and a valve.')).toBeInTheDocument()
    expect(screen.getByText('P-101')).toBeInTheDocument()
  })

  it('vision unavailable (null result) clearly warns', () => {
    render(<VisionResult result={null as unknown as VisionEvidence} />)
    expect(screen.getByText('VISION ANALYSIS UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText(/No visual evidence was obtained/i)).toBeInTheDocument()
  })

  it('vision error discloses the failure reason and does not imply success', () => {
    render(<VisionResult result={failedResult} errors={['vision:Connection error.']} />)
    expect(screen.getByText('VISION ANALYSIS UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText('vision_error: Connection error.')).toBeInTheDocument()
    expect(screen.queryByText(/VISUAL ANALYSIS · AVAILABLE/i)).not.toBeInTheDocument()
  })

  it('zero-confidence vision discloses unavailability', () => {
    render(<VisionResult result={zeroConfidenceResult} />)
    expect(screen.getByText('VISION ANALYSIS UNAVAILABLE')).toBeInTheDocument()
    expect(screen.queryByText(/VISUAL ANALYSIS · AVAILABLE/i)).not.toBeInTheDocument()
  })

  it('RAG-only verified result shows no vision success/warning when no vision result', () => {
    const { container } = render(
      <div>
        <p>KNOWLEDGE RETRIEVAL</p>
        <VisionResult result={null as unknown as VisionEvidence} />
      </div>,
    )
    expect(screen.getByText('KNOWLEDGE RETRIEVAL')).toBeInTheDocument()
    // The RAG answer stays visible; vision is explicitly UNAVAILABLE rather than silently VERIFIED.
    expect(screen.getByText('VISION ANALYSIS UNAVAILABLE')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/visual analysis · available/i)
  })

  it('multimodal result with both vision + RAG shows vision AVAILABLE when vision succeeds', () => {
    const { container } = render(
      <div>
        <p>KNOWLEDGE RETRIEVAL</p>
        <VisionResult result={successResult} />
      </div>,
    )
    expect(screen.getByText('KNOWLEDGE RETRIEVAL')).toBeInTheDocument()
    expect(screen.getByText(/VISUAL ANALYSIS · AVAILABLE/i)).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/unavailable/i)
  })
})
