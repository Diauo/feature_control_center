<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest, downloadFile } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature, Paginated, Pagination } from '@/types'

const session = useSessionStore()
const router = useRouter()
const features = ref<CustomerFeature[]>([])
const loading = ref(false)
const busyId = ref<string | null>(null)
const error = ref('')
const search = ref('')
const statusFilter = ref('')
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const displayedScope = ref('')
let requestSequence = 0

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 11) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
const readyCount = computed(() => features.value.filter((item) => item.status === 'ACTIVE' && item.configurationComplete).length)
const scopeReady = computed(() => displayedScope.value === (session.isAllCustomers ? 'all' : session.currentCustomerId ?? ''))
const statusCopy: Record<CustomerFeature['status'], string> = {
  ACTIVE: '可运行', PREPARING: '准备依赖中', WAITING_DATA_SOURCE: '等待数据源',
  DEPENDENCY_FAILED: '依赖准备失败', DISABLED: '已停用',
}
const runStatusCopy: Record<string, string> = {
  QUEUED: '排队中', STARTING: '启动中', RUNNING: '运行中', STOPPING: '停止中',
}
const stopTarget = ref<CustomerFeature | null>(null)
const stopBusy = ref(false)
const stopError = ref('')
const stopRefreshTimers: number[] = []

function stopDisabled(feature: CustomerFeature): boolean {
  return !scopeReady.value || loading.value || busyId.value === feature.id || stopBusy.value
    || !feature.activeRun || feature.activeRun.status === 'STOPPING'
}

function stopButtonTitle(feature: CustomerFeature): string {
  if (!feature.activeRun) return '当前没有运行中的任务'
  if (feature.activeRun.status === 'STOPPING') return '停止请求已发出，正在等待脚本安全收尾'
  return '立即停止该功能所有运行中的任务'
}

function openStop(feature: CustomerFeature): void {
  stopError.value = ''
  stopTarget.value = feature
}

function closeStop(): void {
  if (stopBusy.value) return
  stopTarget.value = null
}

function scheduleStopRefresh(): void {
  stopRefreshTimers.forEach((timer) => window.clearTimeout(timer))
  stopRefreshTimers.length = 0
  for (const delay of [2500, 12000, 20000]) {
    stopRefreshTimers.push(window.setTimeout(() => { void load() }, delay))
  }
}

async function confirmStop(): Promise<void> {
  const feature = stopTarget.value
  if (!feature) return
  stopBusy.value = true
  stopError.value = ''
  try {
    const result = await apiRequest<{ count: number }>(
      `/api/customer-features/${feature.id}/runs/stop`,
      { method: 'POST' },
    )
    stopTarget.value = null
    if (result.count > 0) {
      notify.success(`已请求停止 ${result.count} 个任务`, {
        description: `${feature.customerName} · ${feature.name} · 脚本正在安全收尾`,
      })
    } else {
      notify.success('当前没有运行中的任务', { description: `${feature.customerName} · ${feature.name}` })
    }
    await load()
    scheduleStopRefresh()
  } catch (reason) {
    stopError.value = reason instanceof ApiError ? reason.message : '停止请求失败，请稍后重试'
  } finally {
    stopBusy.value = false
  }
}

async function load(): Promise<void> {
  const customerId = session.currentCustomerId
  if (!customerId && !session.isAllCustomers) return
  const sequence = ++requestSequence
  loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({
      scope: session.isAllCustomers ? 'all' : 'customer',
      page: String(pagination.value.page), pageSize: String(pagination.value.pageSize),
    })
    if (!session.isAllCustomers && customerId) query.set('customerId', customerId)
    if (session.isAllCustomers && search.value.trim()) query.set('search', search.value.trim())
    if (session.isAllCustomers && statusFilter.value) query.set('status', statusFilter.value)
    const result = await apiRequest<Paginated<CustomerFeature>>(`/api/customer-features?${query}`)
    if (sequence !== requestSequence) return
    features.value = result.items
    pagination.value = result.pagination
    displayedScope.value = session.isAllCustomers ? 'all' : customerId ?? ''
  } catch (reason) {
    if (sequence !== requestSequence) return
    error.value = reason instanceof ApiError ? reason.message : '功能列表加载失败'
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function applyFilters(): void { pagination.value.page = 1; void load() }
function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }

async function replaceDataSource(feature: CustomerFeature, event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busyId.value = feature.id
  error.value = ''
  try {
    const body = new FormData(); body.append('file', file)
    await apiRequest(`/api/customer-features/${feature.id}/data-source`, { method: 'PUT', body })
    await load()
    notify.success('数据源已替换', { description: `${feature.customerName} · ${feature.name} · ${file.name}` })
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '数据源替换失败'
    notify.error('数据源替换失败', { description: error.value })
  } finally { busyId.value = null; input.value = '' }
}

async function downloadDataSource(feature: CustomerFeature): Promise<void> {
  error.value = ''
  try {
    await downloadFile(`/api/customer-features/${feature.id}/data-source/download`)
    notify.success('数据源已开始下载', { description: `${feature.customerName} · ${feature.name}` })
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '数据源下载失败'
    notify.error('数据源下载失败', { description: error.value })
  }
}

async function startRun(feature: CustomerFeature): Promise<void> {
  busyId.value = feature.id; error.value = ''
  try {
    const result = await apiRequest<{ run: { requestId: string } }>(`/api/customer-features/${feature.id}/runs`, { method: 'POST' })
    if (session.hasMenu('runs')) {
      notify.success('任务已提交', { description: `${feature.customerName} · 正在打开实时日志` })
      await router.push(`/runs/${result.run.requestId}`)
    } else {
      notify.success('任务已提交', { description: `${feature.customerName} · 任务已开始执行` })
    }
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '任务创建失败'
    notify.error('任务提交失败', { description: error.value })
  } finally { busyId.value = null }
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / 1024 / 1024).toFixed(1)} MiB`
}


watch([() => session.currentCustomerId, () => session.customerScopeMode], () => {
  if (!session.isAllCustomers) {
    search.value = ''
    statusFilter.value = ''
  }
  pagination.value.page = 1
  void load()
}, { immediate: true })

onBeforeUnmount(() => {
  stopRefreshTimers.forEach((timer) => window.clearTimeout(timer))
})

</script>

<template>
  <section>
    <div class="page-heading"><div><h1>{{ greeting }}，{{ session.user?.displayName }}</h1><p>当前正在查看 {{ session.isAllCustomers ? '全部授权客户' : session.currentCustomer?.name ?? '尚未选择客户' }} 的功能与独立数据源。</p></div></div>
    <div class="metric-grid">
      <article class="metric-card metric-card--primary"><div class="metric-card__topline"><span>已登记功能</span></div><strong>{{ pagination.total }}</strong><p>代码版本共享，客户配置与数据源独立</p></article>
      <article class="metric-card"><span>满足运行条件</span><strong>{{ readyCount }}</strong><p>当前页可立即运行的功能</p></article>
      <article class="metric-card"><span>{{ session.isAllCustomers ? '客户范围' : '当前客户' }}</span><strong class="metric-card__name">{{ session.isAllCustomers ? `${session.customers.length} 个客户` : session.currentCustomer?.name ?? '—' }}</strong><p>后端会在每次请求重新校验权限</p></article>
    </div>
    <form v-if="session.isAllCustomers" class="content-card dashboard-filter" @submit.prevent="applyFilters"><label class="field"><span>搜索</span><input v-model="search" placeholder="客户名称或功能名称" /></label><label class="field"><span>状态</span><select v-model="statusFilter"><option value="">全部状态</option><option value="ACTIVE">可运行</option><option value="WAITING_DATA_SOURCE">等待数据源</option><option value="DEPENDENCY_FAILED">依赖失败</option><option value="DISABLED">已停用</option></select></label><button class="primary-button" type="submit" :disabled="loading">查询</button></form>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <div class="dashboard-results" :class="{ 'dashboard-results--loading': loading || !scopeReady }">
      <div v-if="loading" class="dashboard-loading" role="status">正在切换客户范围…</div>
      <div v-else-if="!scopeReady" class="dashboard-loading" role="status">切换失败，旧数据仅供查看</div>
      <Transition name="scope" mode="out-in">
        <article v-if="!loading && features.length === 0" :key="`empty-${displayedScope}`" class="content-card empty-state-card"><div class="empty-icon">⌘</div><h2>当前范围还没有功能</h2><p>{{ session.isAdmin ? '可以到「功能管理」登记新功能包，或把已有功能复制给当前客户。' : '请联系管理员登记功能。' }}</p></article>
        <div v-else :key="`${displayedScope}-${pagination.page}`" class="feature-grid">
          <article v-for="feature in features" :key="feature.id" class="content-card feature-card">
            <div class="feature-card__header"><div><span v-if="session.isAllCustomers" class="customer-badge">客户：{{ feature.customerName }}</span><h2>{{ feature.name }}</h2></div><span class="status-pill" :class="feature.status === 'ACTIVE' ? 'status-pill--on' : feature.status === 'DEPENDENCY_FAILED' ? 'status-pill--danger' : 'status-pill--warn'">{{ statusCopy[feature.status] }}</span></div>
            <p class="feature-card__description">{{ feature.description || '未提供功能说明' }}</p>
            <dl class="feature-facts"><div><dt>配置</dt><dd>{{ feature.configurationComplete ? '已完整设置' : '仍有必填项未设置' }}</dd></div><div><dt>数据源</dt><dd v-if="feature.dataSource">{{ feature.dataSource.filename }} · 第 {{ feature.dataSource.revisionNumber }} 版 · {{ formatBytes(feature.dataSource.size) }}</dd><dd v-else>{{ feature.dataSourceSchema ? '尚未上传' : '此功能不使用数据源' }}</dd></div></dl>
            <div class="feature-actions">
              <button class="primary-button" type="button" :disabled="!scopeReady || loading || busyId === feature.id || feature.status !== 'ACTIVE' || !feature.configurationComplete" @click="startRun(feature)">{{ busyId === feature.id ? '正在创建…' : '运行' }}</button>
              <button class="danger-button" type="button" :disabled="stopDisabled(feature)" :title="stopButtonTitle(feature)" @click="openStop(feature)">{{ feature.activeRun?.status === 'STOPPING' ? '停止中…' : '急停' }}</button>
              <button v-if="feature.dataSource" class="secondary-button" type="button" :disabled="!scopeReady || loading" @click="downloadDataSource(feature)">下载数据源</button>
              <label v-if="feature.dataSourceSchema" class="secondary-button upload-button" :class="{ 'upload-button--disabled': !scopeReady || loading || busyId === feature.id }">{{ busyId === feature.id ? '上传中…' : '替换数据源' }}<input type="file" :accept="feature.dataSourceSchema.extensions.join(',')" :disabled="!scopeReady || loading || busyId === feature.id" @change="replaceDataSource(feature, $event)" /></label>
            </div>
          </article>
        </div>
      </Transition>
    </div>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />

    <ModalDialog :open="Boolean(stopTarget)" title="急停：停止运行中的任务" description="将立即请求停止该功能当前所有运行中的任务实例；已处理的数据会正常落盘，未完成的部分可稍后重新运行。" width="small" :closeable="!stopBusy" @close="closeStop">
      <div v-if="stopTarget" class="stop-summary">
        <p><strong>{{ stopTarget.customerName }} · {{ stopTarget.name }}</strong></p>
        <p v-if="stopTarget.activeRun">运行中任务：{{ stopTarget.activeRun.requestId }}（{{ runStatusCopy[stopTarget.activeRun.status] ?? stopTarget.activeRun.status }}）</p>
        <p v-else>当前没有运行中的任务。</p>
      </div>
      <p v-if="stopError" class="form-error">{{ stopError }}</p>
      <template #footer>
        <button class="secondary-button" type="button" :disabled="stopBusy" @click="closeStop">取消</button>
        <button class="danger-button" type="button" :disabled="stopBusy" @click="confirmStop">{{ stopBusy ? '正在停止…' : '确认急停' }}</button>
      </template>
    </ModalDialog>
  </section>
</template>
