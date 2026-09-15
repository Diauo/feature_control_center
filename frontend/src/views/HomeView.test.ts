import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { apiRequest } from '@/lib/api'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature } from '@/types'
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
  updatedAt: 1_800_000_000,
}

afterEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('HomeView feature upload entry', () => {
  it('places the generic upload action in the registered-feature summary card', async () => {
    vi.mocked(apiRequest).mockImplementation((async (url: string) => {
      if (url.startsWith('/api/customer-features?')) {
        return {
          items: [feature],
          pagination: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
        }
      }
      if (url === '/api/admin/settings') {
        return { values: { 'feature.allowed_package_formats': ['zip', 'rar'] } }
      }
      throw new Error(`Unexpected request: ${url}`)
    }) as typeof apiRequest)
    const pinia = createPinia()
    const session = useSessionStore(pinia)
    session.user = {
      id: 'admin-1',
      username: 'admin',
      displayName: '管理员',
      role: 'admin',
      mustChangePassword: false,
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
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: HomeView }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(HomeView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.find('.feature-actions').text()).not.toContain('上传功能包')
    expect(wrapper.find('.feature-actions').text()).toContain('配置管理')
    const uploadButton = wrapper.get('.metric-card--primary .metric-card__action')
    expect(uploadButton.text()).toBe('上传功能包')

    await uploadButton.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    expect(document.body.textContent).toContain('上传功能包')
    expect(document.body.textContent).toContain('客户 A')

    wrapper.unmount()
  })
})
