import { describe, expect, it } from 'vitest'

import { MAX_VISIBLE_RUN_EVENTS, RunEventBuffer } from '@/lib/runEventBuffer'
import type { RunEvent } from '@/types'


describe('RunEventBuffer', () => {
  it('orders a batch and ignores duplicate or stale sequences', () => {
    const target: RunEvent[] = []
    const buffer = new RunEventBuffer(10)

    buffer.append(target, [event(2), event(1), event(2)])
    const result = buffer.append(target, [event(2), event(3)])

    expect(target.map((item) => item.sequence)).toEqual([1, 2, 3])
    expect(result).toEqual({ added: 1, omitted: 0, cursor: 3 })
  })

  it('keeps only the latest console window during a large catch-up batch', () => {
    const target: RunEvent[] = []
    const buffer = new RunEventBuffer()
    const incoming = Array.from({ length: 10_000 }, (_, index) => event(index + 1))

    const result = buffer.append(target, incoming)

    expect(target).toHaveLength(MAX_VISIBLE_RUN_EVENTS)
    expect(target[0]?.sequence).toBe(8001)
    expect(target.at(-1)?.sequence).toBe(10_000)
    expect(result).toEqual({ added: 10_000, omitted: 8000, cursor: 10_000 })
  })

  it('accounts for history skipped before the initial request', () => {
    const target: RunEvent[] = []
    const buffer = new RunEventBuffer()
    buffer.reset(8000)

    const result = buffer.append(target, [event(8001), event(8002)])

    expect(result).toEqual({ added: 2, omitted: 8000, cursor: 8002 })
  })
})

function event(sequence: number): RunEvent {
  return {
    requestId: 'run-id',
    sequence,
    occurredAtMs: 1_700_000_000_000 + sequence,
    level: 'INFO',
    source: 'SDK',
    message: `event-${sequence}`,
    context: {},
  }
}
