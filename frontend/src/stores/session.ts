import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { apiRequest, clearCsrfToken, refreshCsrfToken, setCsrfToken } from '@/lib/api'
import type { Customer, SessionPayload, UserSummary } from '@/types'

const CUSTOMER_STORAGE_KEY = 'fcc:last-customer-id'
const CUSTOMER_SCOPE_STORAGE_KEY = 'fcc:customer-scope'

export const useSessionStore = defineStore('session', () => {
  const user = ref<UserSummary | null>(null)
  const customers = ref<Customer[]>([])
  const currentCustomerId = ref<string | null>(null)
  const customerScopeMode = ref<'customer' | 'all'>('customer')
  const initialized = ref(false)
  const setupRequired = ref(false)
  const systemName = ref('功能控制中心')
  const startupError = ref('')

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const currentCustomer = computed(
    () => customers.value.find((customer) => customer.id === currentCustomerId.value) ?? null,
  )
  const selectedCustomerScopeValue = computed(() => customerScopeMode.value === 'all' ? '__all__' : currentCustomerId.value ?? '')
  const isAllCustomers = computed(() => customerScopeMode.value === 'all')

  async function bootstrap(): Promise<void> {
    if (initialized.value) return
    startupError.value = ''
    try {
      const status = await apiRequest<{ needsInitialization: boolean; systemName: string }>('/api/setup/status')
      setupRequired.value = status.needsInitialization
      systemName.value = status.systemName
      await refreshCsrfToken()
      if (!setupRequired.value) {
        await restoreSession()
      }
    } catch {
      clearSession()
      startupError.value = '暂时无法连接服务器，请确认服务已经启动后重试。'
    } finally {
      initialized.value = true
    }
  }

  async function retryBootstrap(): Promise<void> {
    initialized.value = false
    await bootstrap()
  }

  async function restoreSession(): Promise<void> {
    try {
      const payload = await apiRequest<SessionPayload>('/api/me')
      applySession(payload)
    } catch {
      clearSession()
    }
  }

  async function login(username: string, password: string): Promise<void> {
    const payload = await apiRequest<{ user: UserSummary; csrfToken: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setCsrfToken(payload.csrfToken)
    const me = await apiRequest<SessionPayload>('/api/me')
    applySession(me)
  }

  async function initializeSystem(input: {
    bootstrapCode: string
    systemName: string
    adminUsername: string
    adminDisplayName: string
    password: string
    customerName: string
    systemTimezone: string
  }): Promise<void> {
    const payload = await apiRequest<{ user: UserSummary; csrfToken: string }>('/api/setup/initialize', {
      method: 'POST',
      body: JSON.stringify(input),
    })
    setupRequired.value = false
    systemName.value = input.systemName
    setCsrfToken(payload.csrfToken)
    const me = await apiRequest<SessionPayload>('/api/me')
    applySession(me)
  }

  async function logout(): Promise<void> {
    try {
      await apiRequest<{ loggedOut: boolean }>('/api/auth/logout', { method: 'POST' })
    } finally {
      clearSession()
      try {
        await refreshCsrfToken()
      } catch {
        // 本地登录状态必须先清理；服务器恢复后页面会重新获取 CSRF。
      }
    }
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    const payload = await apiRequest<{ passwordChanged: boolean; csrfToken: string }>('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({ currentPassword, newPassword }),
    })
    setCsrfToken(payload.csrfToken)
    const me = await apiRequest<SessionPayload>('/api/me')
    applySession(me)
  }

  async function reauthenticate(password: string): Promise<void> {
    await apiRequest('/api/auth/reauthenticate', {
      method: 'POST',
      body: JSON.stringify({ password }),
    })
  }

  async function reloadCustomers(): Promise<void> {
    const payload = await apiRequest<{ items: Customer[] }>('/api/customers')
    customers.value = payload.items
    selectAvailableCustomer()
  }

  function selectCustomer(customerId: string): void {
    if (customerId === '__all__') {
      customerScopeMode.value = 'all'
      localStorage.setItem(CUSTOMER_SCOPE_STORAGE_KEY, 'all')
      return
    }
    if (!customers.value.some((customer) => customer.id === customerId)) return
    customerScopeMode.value = 'customer'
    currentCustomerId.value = customerId
    localStorage.setItem(CUSTOMER_STORAGE_KEY, customerId)
    localStorage.setItem(CUSTOMER_SCOPE_STORAGE_KEY, 'customer')
  }

  function applySession(payload: SessionPayload): void {
    user.value = payload.user
    customers.value = payload.customers
    setCsrfToken(payload.csrfToken)
    selectAvailableCustomer()
  }

  function selectAvailableCustomer(): void {
    const saved = localStorage.getItem(CUSTOMER_STORAGE_KEY)
    const selected = customers.value.find((customer) => customer.id === saved) ?? customers.value[0] ?? null
    currentCustomerId.value = selected?.id ?? null
    customerScopeMode.value = selected && localStorage.getItem(CUSTOMER_SCOPE_STORAGE_KEY) === 'all' ? 'all' : 'customer'
    if (selected) localStorage.setItem(CUSTOMER_STORAGE_KEY, selected.id)
  }

  function clearSession(): void {
    user.value = null
    customers.value = []
    currentCustomerId.value = null
    customerScopeMode.value = 'customer'
    clearCsrfToken()
  }

  return {
    user,
    customers,
    currentCustomerId,
    customerScopeMode,
    initialized,
    setupRequired,
    systemName,
    startupError,
    isAuthenticated,
    isAdmin,
    currentCustomer,
    selectedCustomerScopeValue,
    isAllCustomers,
    bootstrap,
    retryBootstrap,
    login,
    initializeSystem,
    logout,
    changePassword,
    reauthenticate,
    reloadCustomers,
    selectCustomer,
    clearSession,
  }
})
