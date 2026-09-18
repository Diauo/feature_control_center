import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { apiRequest } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature, MenuKey } from '@/types'
import HomeView from '@/views/HomeView.vue'

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    code: string

    constructor(code: string, message: string) {
      super(message)
      this.code = code
    }
  },
  apiRequest: vi.fn(),
  downloadFile: vi.fn(),
}))

vi.mock('@/lib/notify', () => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const feature: CustomerFeature = {
  id: 'customer-feature-1',
  customerId: 'customer-1',
  customerName: '客户 A',
  definitionId: 'definition-1',
  versionId: 'version-1',
  versionNumber: 1,
  name: '库存同步',
  description: '测试功能',
  isEnabled: true,
  status: 'ACTIVE',
  maxRuntimeSeconds: null,
  configurationComplete: true,
  dataSourceSchema: null,
  dataSource: null,
  activeRun: null,
  updatedAt: 1_800_000_000,
}

const runningFeature: CustomerFeature = {
  ...feature,
  activeRun: { requestId: 'run-9', status: 'RUNNING', queuedAt: 1_800_000_010, startedAt: 1_800_000_012 },
}

function mockLoadOnly() {
  vi.mocked(apiRequest).mockImplementation((async (url: string) => {
    if (url.startsWith('/api/customer-features?')) {
      return {
        items: [feature],
        pagination: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
      }
    }
    throw new Error(`Unexpected request: ${url}`)
  }) as typeof apiRequest)
}

function mockLoadAndRun() {
  vi.mocked(apiRequest).mockImplementation((async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/customer-features?')) {
      return {
        items: [feature],
        pagination: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
      }
    }
    if (url.endsWith('/runs') && init?.method === 'POST') {
      return { run: { requestId: 'run-1' } }
    }
    throw new Error(`Unexpected request: ${url}`)
  }) as typeof apiRequest)
}

function mockLoadAndStop() {
  vi.mocked(apiRequest).mockImplementation((async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/customer-features?')) {
      return {
        items: [runningFeature],
        pagination: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
      }
    }
    if (url.endsWith('/runs/stop') && init?.method === 'POST') {
      return { count: 1, runs: [{ requestId: 'run-9', status: 'STOPPING' }] }
    }
    throw new Error(`Unexpected request: ${url}`)
  }) as typeof apiRequest)
}

async function mountHome(menuKeys: MenuKey[], routes: RouteRecordRaw[] = [{ path: '/', component: HomeView }]) {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.user = {
    id: 'user-1',
    username: 'user',
    displayName: '用户',
    role: 'operator',
    mustChangePassword: false,
    menuKeys,
  }
  session.customers = [{
    id: 'customer-1',
    name: '客户 A',
    description: '测试客户',
    isActive: true,
    createdAt: 1_800_000_000,
    updatedAt: 1_800_000_000,
  }]
  session.currentCustomerId = 'customer-1'
  session.customerScopeMode = 'customer'
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(HomeView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router }
}

afterEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('HomeView 职责边界', () => {
  it('不再提供上传功能包与配置管理入口', async () => {
    mockLoadOnly()
    const { wrapper } = await mountHome(['workspace', 'runs'])
    expect(wrapper.find('.metric-card__action').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('上传功能包')
    expect(wrapper.find('.feature-actions').text()).not.toContain('配置管理')
    expect(wrapper.find('.feature-actions').text()).toContain('运行')
    wrapper.unmount()
  })

  it('有运行记录菜单时，运行后跳转实时日志', async () => {
    mockLoadAndRun()
    const { wrapper, router } = await mountHome(['workspace', 'runs'], [
      { path: '/', component: HomeView },
      { path: '/runs/:requestId', component: { template: '<div>run</div>' } },
    ])
    await wrapper.get('.feature-actions .primary-button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/runs/run-1')
    wrapper.unmount()
  })

  it('没有运行记录菜单时，运行后不跳转仅提示', async () => {
    mockLoadAndRun()
    const { wrapper, router } = await mountHome(['workspace'])
    await wrapper.get('.feature-actions .primary-button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    expect(vi.mocked(notify.success)).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('有运行中任务时急停按钮可用，确认后请求停止全部实例', async () => {
    mockLoadAndStop()
    const { wrapper } = await mountHome(['workspace'])
    const stopButton = wrapper.get('.feature-actions .danger-button')
    expect(stopButton.attributes('disabled')).toBeUndefined()
    await stopButton.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('急停')
    const confirmButton = Array.from(document.body.querySelectorAll('button')).find((item) =>
      item.textContent?.includes('确认急停'),
    )
    expect(confirmButton).toBeTruthy()
    confirmButton!.click()
    await flushPromises()
    expect(vi.mocked(apiRequest)).toHaveBeenCalledWith(
      '/api/customer-features/customer-feature-1/runs/stop',
      { method: 'POST' },
    )
    expect(vi.mocked(notify.success)).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('没有运行中任务时急停按钮禁用', async () => {
    mockLoadOnly()
    const { wrapper } = await mountHome(['workspace', 'runs'])
    const stopButton = wrapper.get('.feature-actions .danger-button')
    expect(stopButton.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
