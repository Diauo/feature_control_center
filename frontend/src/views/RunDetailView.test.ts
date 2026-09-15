import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import RunDetailView from '@/views/RunDetailView.vue'
import type { RunEvent, RunReportSummary, RunSummary } from '@/types'


const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { requestId: 'run-id' } }),
  useRouter: () => ({ push: mocks.push }),
}))

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
  apiRequest: mocks.apiRequest,
  downloadFile: vi.fn(),
}))

vi.mock('@/lib/notify', () => ({
  notify: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

class FakeEventSource {
  static latest: FakeEventSource | null = null
  readonly listeners = new Map<string, Array<(event: MessageEvent) => void>>()
  closed = false
  onerror: (() => void) | null = null

  constructor(readonly url: string) { FakeEventSource.latest = this }

  addEventListener(name: string, listener: EventListenerOrEventListenerObject): void {
    const callback = typeof listener === 'function'
      ? listener as (event: MessageEvent) => void
      : (event: MessageEvent) => listener.handleEvent(event)
    const callbacks = this.listeners.get(name) ?? []
    callbacks.push(callback)
    this.listeners.set(name, callbacks)
  }

  close(): void { this.closed = true }

  emit(name: string, data: unknown): void {
    const event = new MessageEvent(name, { data: JSON.stringify(data) })
    for (const listener of this.listeners.get(name) ?? []) listener(event)
  }
}

describe('RunDetailView', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    FakeEventSource.latest = null
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('seals a terminal stream after one bounded render and keeps navigation responsive', async () => {
    const running = runSummary('RUNNING', 0)
    const succeeded = runSummary('SUCCEEDED', 2100)
    let runFetchCount = 0
    mocks.apiRequest.mockImplementation(async (path: string) => {
      if (path.includes('/events?')) return { items: [] }
      if (path === '/api/runs/run-id/report') return { report: null }
      if (path === '/api/runs/run-id') {
        runFetchCount += 1
        return { run: runFetchCount > 1 ? succeeded : running }
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0))
    vi.stubGlobal('cancelAnimationFrame', (handle: number) => window.clearTimeout(handle))

    const wrapper = mount(RunDetailView, { attachTo: document.body })
    await flushPromises()
    const source = FakeEventSource.latest
    expect(source?.url).toBe('/api/runs/run-id/events/stream?after=0')

    for (let sequence = 1; sequence <= 2100; sequence += 1) source?.emit('log', runEvent(sequence))
    source?.emit('run', { status: 'SUCCEEDED', latestSequence: 2100 })
    await flushPromises()

    expect(source?.closed).toBe(true)
    expect(wrapper.findAll('.log-line')).toHaveLength(2000)
    expect(wrapper.find('.console-limit-notice').text()).toContain('完整日志仍可下载')
    expect(wrapper.text()).toContain('已省略 100 条')
    await wrapper.get('.run-heading__actions .secondary-button').trigger('click')
    expect(mocks.push).toHaveBeenCalledWith('/runs')
    wrapper.unmount()
  })

  it('shows report summary and item statuses in business-facing Chinese', async () => {
    const report: RunReportSummary = {
      title: '库存同步结果', itemLabel: '商品',
      columns: [
        { key: 'sku', label: '商品编码', type: 'string' },
        { key: 'storeCode', label: '店铺编码', type: 'string' },
      ],
      status: 'COMPLETE', expectedTotal: 2, reportedTotal: 2, total: 2,
      successCount: 1, failedCount: 1, noDataCount: 0, skippedCount: 0,
      unfinishedCount: 0, unreportedCount: 0, validationErrorCount: 0,
      startedAt: 1_700_000_000, completedAt: 1_700_000_100, detailsPurgedAt: null,
    }
    const succeeded = { ...runSummary('SUCCEEDED', 0), report }
    mocks.apiRequest.mockImplementation(async (path: string) => {
      if (path === '/api/runs/run-id') return { run: succeeded }
      if (path === '/api/runs/run-id/report') return { report }
      if (path.includes('/report/items?')) {
        return {
          items: [
            { sequence: 1, status: 'SUCCESS', reason: '同步成功', values: { sku: 'SKU-001', storeCode: 'CK001' }, reportedAtMs: 1_700_000_010_000 },
            { sequence: 2, status: 'FAILED', reason: '接口超时', values: { sku: 'SKU-002', storeCode: 'CK002' }, reportedAtMs: 1_700_000_020_000 },
          ],
          pagination: { page: 1, pageSize: 20, total: 2, totalPages: 1 },
        }
      }
      if (path.includes('/events?')) return { items: [] }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0))
    vi.stubGlobal('cancelAnimationFrame', (handle: number) => window.clearTimeout(handle))

    const wrapper = mount(RunDetailView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.text()).toContain('库存同步结果')
    expect(wrapper.text()).toContain('成功1')
    expect(wrapper.text()).toContain('失败1')
    expect(wrapper.text()).toContain('SKU-002')
    expect(wrapper.text()).toContain('接口超时')
    expect(wrapper.text()).not.toContain('FAILED_INTERRUPTED')
    wrapper.unmount()
  })
})

function runSummary(status: RunSummary['status'], latestSequence: number): RunSummary {
  return {
    requestId: 'run-id', customerId: 'customer-id', customerName: '测试客户',
    customerFeatureId: 'customer-feature-id', featureVersionId: 'version-id', featureName: '日志测试',
    versionNumber: 1, dataSourceRevisionId: null, dataSourceFilename: null, triggerSource: 'MANUAL',
    status, queuedAt: 1_700_000_000, claimedAt: null, startedAt: null, stopRequestedAt: null,
    finishedAt: status === 'SUCCEEDED' ? 1_700_000_100 : null, exitCode: status === 'SUCCEEDED' ? 0 : null,
    failureSummary: null, stopReason: null, maxRuntimeSeconds: null, latestSequence,
    finalSequence: status === 'SUCCEEDED' ? latestSequence : null, logsPurgedAt: null, report: null,
  }
}

function runEvent(sequence: number): RunEvent {
  return {
    requestId: 'run-id', sequence, occurredAtMs: 1_700_000_000_000 + sequence,
    level: 'INFO', source: 'SDK', message: `测试日志 ${sequence}`, context: {},
  }
}
