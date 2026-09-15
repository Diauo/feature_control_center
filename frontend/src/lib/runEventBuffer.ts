import type { RunEvent } from '@/types'


export const MAX_VISIBLE_RUN_EVENTS = 2000

export interface RunEventAppendResult {
  added: number
  omitted: number
  cursor: number
}

/**
 * Keeps the browser-side console bounded without changing the persisted run log.
 * Run event sequences are monotonic, so a cursor is enough to reject reconnect duplicates.
 */
export class RunEventBuffer {
  private cursorValue = 0
  private omittedValue = 0

  constructor(private readonly limit = MAX_VISIBLE_RUN_EVENTS) {
    if (!Number.isInteger(limit) || limit < 1) throw new RangeError('Run event buffer limit must be a positive integer')
  }

  get cursor(): number { return this.cursorValue }

  get omitted(): number { return this.omittedValue }

  reset(startAfter = 0): void {
    const cursor = Math.max(0, Math.trunc(startAfter))
    this.cursorValue = cursor
    this.omittedValue = cursor
  }

  append(target: RunEvent[], incoming: readonly RunEvent[]): RunEventAppendResult {
    if (incoming.length === 0) return this.result(0)

    const ordered = incoming.length === 1
      ? incoming
      : [...incoming].sort((left, right) => left.sequence - right.sequence)
    let added = 0
    for (const event of ordered) {
      if (event.sequence <= this.cursorValue) continue
      target.push(event)
      this.cursorValue = event.sequence
      added += 1
    }

    const overflow = Math.max(0, target.length - this.limit)
    if (overflow > 0) {
      target.splice(0, overflow)
      this.omittedValue += overflow
    }
    return this.result(added)
  }

  private result(added: number): RunEventAppendResult {
    return { added, omitted: this.omittedValue, cursor: this.cursorValue }
  }
}
