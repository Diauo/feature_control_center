<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest } from '@/lib/api'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature, Paginated, Pagination, RunStatus, RunSummary } from '@/types'

const session = useSessionStore()
const runs = ref<RunSummary[]>([])
const features = ref<CustomerFeature[]>([])
const loading = ref(false)
const error = ref('')
const filters = ref({ requestId: '', customerFeatureId: '', status: '', triggerSource: '', queuedFrom: '', queuedTo: '' })
let timer: number | null = null
let requestSequence = 0
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })

const activeCount = computed(() => runs.value.filter((item) => ['QUEUED', 'STARTING', 'RUNNING', 'STOPPING'].includes(item.status)).length)
const hasFilters = computed(() => Object.values(filters.value).some(Boolean))
const statusCopy: Record<RunStatus, string> = {
  QUEUED: '排队中', STARTING: '正在启动', RUNNING: '运行中', STOPPING: '停止中',
  SUCCEEDED: '已完成', FAILED: '执行失败', STOPPED: '已停止', TIMED_OUT: '已超时', INTERRUPTED: '已中断',
}

async function load(silent = false): Promise<void> {
  const customerId = session.currentCustomerId
  const allCustomers = session.isAllCustomers
  const sequence = ++requestSequence
  if (!customerId && !allCustomers) { runs.value = []; features.value = []; loading.value = false; return }
  if (!silent) loading.value = true
  try {
    const query = new URLSearchParams({
      scope: allCustomers ? 'all' : 'customer',
      page: String(pagination.value.page), pageSize: String(pagination.value.pageSize),
    })
    if (!allCustomers && customerId) query.set('customerId', customerId)
    if (filters.value.requestId.trim()) query.set('requestId', filters.value.requestId.trim())
    if (filters.value.customerFeatureId) query.set('customerFeatureId', filters.value.customerFeatureId)
    if (filters.value.status) query.set('status', filters.value.status)
    if (filters.value.triggerSource) query.set('triggerSource', filters.value.triggerSource)
    if (filters.value.queuedFrom) query.set('queuedFrom', String(toEpoch(filters.value.queuedFrom)))
    if (filters.value.queuedTo) query.set('queuedTo', String(toEpoch(filters.value.queuedTo)))
    const [runResult, featureResult] = await Promise.all([
      apiRequest<Paginated<RunSummary>>(`/api/runs?${query.toString()}`),
      allCustomers ? Promise.resolve({ items: [] as CustomerFeature[] }) : features.value.length
        ? Promise.resolve({ items: features.value })
        : apiRequest<{ items: CustomerFeature[] }>(`/api/customers/${encodeURIComponent(customerId!)}/features`),
    ])
    if (sequence !== requestSequence) return
    runs.value = runResult.items
    pagination.value = runResult.pagination
    features.value = featureResult.items
    error.value = ''
  } catch (reason) {
    if (sequence !== requestSequence) return
    error.value = reason instanceof ApiError ? reason.message : '运行记录加载失败'
  } finally { if (sequence === requestSequence) loading.value = false }
}

function resetFilters(): void {
  filters.value = { requestId: '', customerFeatureId: '', status: '', triggerSource: '', queuedFrom: '', queuedTo: '' }
  pagination.value.page = 1
  void load()
}
function applyFilters(): void { pagination.value.page = 1; void load() }
function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }

function toEpoch(value: string): number { return Math.floor(new Date(value).getTime() / 1000) }

function statusClass(status: RunStatus): string {
  if (status === 'SUCCEEDED') return 'status-pill--on'
  if (['FAILED', 'TIMED_OUT', 'INTERRUPTED'].includes(status)) return 'status-pill--danger'
  if (['QUEUED', 'STARTING', 'RUNNING', 'STOPPING'].includes(status)) return 'status-pill--warn'
  return 'status-pill--off'
}

function formatTime(value: number | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(value * 1000)
}

function reportSummary(run: RunSummary): string {
  const active = ['QUEUED', 'STARTING', 'RUNNING', 'STOPPING'].includes(run.status)
  if (!run.report) return active ? '尚未生成' : '未提交报表'
  if (active) {
    const expected = run.report.expectedTotal == null ? '' : ` / 预计 ${run.report.expectedTotal}`
    return `已处理 ${run.report.reportedTotal}${expected} · 成功 ${run.report.successCount} · 失败 ${run.report.failedCount}`
  }
  return `总数 ${run.report.total} · 成功 ${run.report.successCount} · 失败 ${run.report.failedCount}`
}

function reportSecondary(run: RunSummary): string {
  if (!run.report) return ''
  const parts = [`无数据 ${run.report.noDataCount}`, `跳过 ${run.report.skippedCount}`]
  if (!['QUEUED', 'STARTING', 'RUNNING', 'STOPPING'].includes(run.status)) {
    if (run.report.unfinishedCount > 0) parts.push(`未完成 ${run.report.unfinishedCount}`)
    if (run.report.status === 'INCOMPLETE') parts.push('报表未完整')
  }
  return parts.join(' · ')
}

function scheduleRefresh(): void {
  if (timer !== null) window.clearInterval(timer)
  timer = window.setInterval(() => { if (activeCount.value > 0) void load(true) }, 3000)
}

watch([() => session.currentCustomerId, () => session.customerScopeMode], async () => {
  pagination.value.page = 1
  features.value = []
  filters.value = { requestId: '', customerFeatureId: '', status: '', triggerSource: '', queuedFrom: '', queuedTo: '' }
  await load()
  scheduleRefresh()
}, { immediate: true })
onBeforeUnmount(() => { if (timer !== null) window.clearInterval(timer) })
</script>

<template>
  <section>
    <div class="page-heading"><div><h1>运行记录</h1><p>{{ session.isAllCustomers ? '全部授权客户' : session.currentCustomer?.name ?? '当前客户' }} 的任务状态、业务结果与最终日志。支持按运行事实筛选，但不对脚本业务内容做全文检索。</p></div><button class="secondary-button" type="button" :disabled="loading" @click="load()">刷新</button></div>
    <div class="metric-grid">
      <article class="metric-card metric-card--primary"><span>匹配记录</span><strong>{{ pagination.total }}</strong><p>结果按页加载</p></article>
      <article class="metric-card"><span>正在处理</span><strong>{{ activeCount }}</strong><p>包含排队、启动、运行与停止中</p></article>
      <article class="metric-card"><span>日志来源</span><strong class="metric-card__name">实时事件流</strong><p>SDK、stdout、stderr 与平台生命周期</p></article>
    </div>
    <article class="content-card run-filter-card">
      <header><div><h2>筛选运行记录</h2><p>请求 ID 支持前缀或完整值；时间按浏览器本地时间输入。</p></div><button v-if="hasFilters" class="text-button" type="button" @click="resetFilters">清除筛选</button></header>
      <form class="run-filter-grid" @submit.prevent="applyFilters">
        <label class="field"><span>请求 ID</span><input v-model="filters.requestId" maxlength="32" pattern="[0-9a-fA-F]{1,32}" placeholder="输入十六进制前缀" /></label>
        <label class="field"><span>功能</span><select v-model="filters.customerFeatureId" :disabled="session.isAllCustomers"><option value="">{{ session.isAllCustomers ? '全部客户模式下按全部功能' : '全部功能' }}</option><option v-for="feature in features" :key="feature.id" :value="feature.id">{{ feature.name }}</option></select></label>
        <label class="field"><span>运行状态</span><select v-model="filters.status"><option value="">全部状态</option><option v-for="(label, value) in statusCopy" :key="value" :value="value">{{ label }}</option></select></label>
        <label class="field"><span>触发方式</span><select v-model="filters.triggerSource"><option value="">全部方式</option><option value="MANUAL">手动运行</option><option value="SCHEDULED">定时触发</option></select></label>
        <label class="field"><span>进入队列：从</span><input v-model="filters.queuedFrom" type="datetime-local" /></label>
        <label class="field"><span>进入队列：到</span><input v-model="filters.queuedTo" type="datetime-local" /></label>
        <button class="primary-button filter-submit" type="submit" :disabled="loading">查询</button>
      </form>
    </article>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <div v-if="loading" class="content-card loading-state">正在读取运行记录…</div>
    <article v-else-if="runs.length === 0" class="content-card empty-state-card"><div class="empty-icon">▶</div><h2>{{ hasFilters ? '没有匹配的运行记录' : '还没有运行记录' }}</h2><p>{{ hasFilters ? '调整筛选条件后重新查询。' : '从工作台选择一个满足运行条件的功能，点击“运行”。' }}</p></article>
    <article v-else class="content-card table-card"><div class="table-scroll"><table><thead><tr><th v-if="session.isAllCustomers">客户</th><th>功能</th><th>请求 ID</th><th>执行状态</th><th>业务结果</th><th>进入队列</th><th>完成</th><th class="align-right">操作</th></tr></thead><tbody>
          <tr v-for="run in runs" :key="run.requestId"><td v-if="session.isAllCustomers"><span class="customer-badge">{{ run.customerName }}</span></td><td><strong>{{ run.featureName }}</strong><small class="block-copy">代码版本 {{ run.versionNumber }} · {{ run.triggerSource === 'MANUAL' ? '手动' : '定时' }}</small></td><td class="mono-cell">{{ run.requestId }}</td><td><span class="status-pill" :class="statusClass(run.status)">{{ statusCopy[run.status] }}</span><small v-if="run.logsPurgedAt" class="block-copy">日志已清理</small></td><td><strong class="run-report-summary">{{ reportSummary(run) }}</strong><small v-if="reportSecondary(run)" class="block-copy">{{ reportSecondary(run) }}</small></td><td class="nowrap">{{ formatTime(run.queuedAt) }}</td><td class="nowrap">{{ formatTime(run.finishedAt) }}</td><td class="align-right"><RouterLink class="text-link" :to="`/runs/${run.requestId}`">查看详情</RouterLink></td></tr>
    </tbody></table></div></article>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />
  </section>
</template>
