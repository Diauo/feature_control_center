import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from '@/lib/api'
import { useSessionStore } from '@/stores/session'
import type { RunReportSummary, RunStatus, RunSummary } from '@/types'
import RunsView from '@/views/RunsView.vue'


vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
  apiRequest: vi.fn(),
}))

afterEach(() => {
  vi.clearAllMocks()
})

describe('RunsView business summaries', () => {
  it('distinguishes live progress from terminal totals', async () => {
    const running = runSummary('RUNNING', reportSummary({
      status: 'OPEN', expectedTotal: 1000, reportedTotal: 368,
      successCount: 350, failedCount: 8, noDataCount: 6, skippedCount: 4,
      unfinishedCount: 632, unreportedCount: 632,
    }))
    const completed = runSummary('SUCCEEDED', reportSummary({
      status: 'COMPLETE', expectedTotal: 1000, reportedTotal: 1000,
      successCount: 980, failedCount: 12, noDataCount: 5, skippedCount: 3,
      unfinishedCount: 0, unreportedCount: 0,
    }))
    vi.mocked(apiRequest).mockImplementation((async (url: string) => {
      if (url.startsWith('/api/runs?')) {
        return {
          items: [running, completed],
          pagination: { page: 1, pageSize: 20, total: 2, totalPages: 1 },
        }
      }
      if (url === '/api/customers/customer-1/features') return { items: [] }
      throw new Error(`Unexpected request: ${url}`)
    }) as typeof apiRequest)

    const pinia = createPinia()
    const session = useSessionStore(pinia)
    session.user = {
      id: 'admin-1', username: 'admin', displayName: '管理员', role: 'admin', mustChangePassword: false,
    }
    session.customers = [{
      id: 'customer-1', name: '客户 A', description: '', isActive: true,
      createdAt: 1_800_000_000, updatedAt: 1_800_000_000,
    }]
    session.currentCustomerId = 'customer-1'
    session.customerScopeMode = 'customer'

    const wrapper = mount(RunsView, {
      global: {
        plugins: [pinia],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    const primary = wrapper.findAll('.run-report-summary').map((node) => node.text())
    expect(primary).toEqual([
      '已处理 368 / 预计 1000 · 成功 350 · 失败 8',
      '总数 1000 · 成功 980 · 失败 12',
    ])
    const rows = wrapper.findAll('tbody tr')
    expect(rows[0]!.text()).not.toContain('未完成 632')
    expect(rows[1]!.text()).toContain('无数据 5 · 跳过 3')
    wrapper.unmount()
  })
})

function reportSummary(overrides: Partial<RunReportSummary>): RunReportSummary {
  return {
    title: '库存同步结果', itemLabel: '商品',
    columns: [{ key: 'sku', label: '商品编码', type: 'string' }],
    status: 'COMPLETE', expectedTotal: 0, reportedTotal: 0, total: overrides.expectedTotal ?? 0,
    successCount: 0, failedCount: 0, noDataCount: 0, skippedCount: 0,
    unfinishedCount: 0, unreportedCount: 0, validationErrorCount: 0,
    startedAt: 1_800_000_000, completedAt: null, detailsPurgedAt: null,
    ...overrides,
  }
}

function runSummary(status: RunStatus, report: RunReportSummary): RunSummary {
  return {
    requestId: `${status.toLowerCase()}-request`, customerId: 'customer-1', customerName: '客户 A',
    customerFeatureId: 'feature-1', featureVersionId: 'version-1', featureName: '库存同步',
    versionNumber: 1, dataSourceRevisionId: null, dataSourceFilename: null, triggerSource: 'MANUAL',
    status, queuedAt: 1_800_000_000, claimedAt: 1_800_000_001, startedAt: 1_800_000_002,
    stopRequestedAt: null, finishedAt: status === 'SUCCEEDED' ? 1_800_000_100 : null,
    exitCode: status === 'SUCCEEDED' ? 0 : null, failureSummary: null, stopReason: null,
    maxRuntimeSeconds: null, latestSequence: 8, finalSequence: status === 'SUCCEEDED' ? 8 : null,
    logsPurgedAt: null, report,
  }
}
