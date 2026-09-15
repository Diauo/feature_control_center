<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature, Paginated, Pagination, Schedule, ScheduleOutcome } from '@/types'

type ScheduleMode = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'CRON'

const session = useSessionStore()
const schedules = ref<Schedule[]>([])
const features = ref<CustomerFeature[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const modalOpen = ref(false)
const editingId = ref<string | null>(null)
const editingCustomerId = ref<string | null>(null)
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
let requestSequence = 0
const form = ref({
  name: '', customerFeatureId: '', mode: 'DAILY' as ScheduleMode,
  time: '09:00', weekday: 1, monthday: 1, cronExpression: '0 9 * * *', isEnabled: true,
})

const outcomeCopy: Record<ScheduleOutcome, string> = {
  ENQUEUED: '已入队', MISSED: '已错过', SKIPPED_ACTIVE: '已有任务，已跳过',
  SKIPPED_UNAVAILABLE: '功能不可用，已跳过', QUEUE_FULL: '队列已满', DUPLICATE: '已防重复',
}
const activeCount = computed(() => schedules.value.filter((item) => item.isEnabled).length)
const timezone = computed(() => schedules.value[0]?.timezone ?? '系统设置时区')

watch([() => session.currentCustomerId, () => session.customerScopeMode], () => { pagination.value.page = 1; void load() }, { immediate: true })

async function load(): Promise<void> {
  const customerId = session.currentCustomerId
  const allCustomers = session.isAllCustomers
  const sequence = ++requestSequence
  modalOpen.value = false
  if (!customerId && !allCustomers) { schedules.value = []; features.value = []; loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    const [scheduleResult, featureResult] = await Promise.all([
      apiRequest<Paginated<Schedule>>(`/api/schedules?scope=${allCustomers ? 'all' : 'customer'}${!allCustomers && customerId ? `&customerId=${encodeURIComponent(customerId)}` : ''}&page=${pagination.value.page}&pageSize=${pagination.value.pageSize}`),
      allCustomers ? Promise.resolve({ items: [] as CustomerFeature[] }) : apiRequest<{ items: CustomerFeature[] }>(`/api/customers/${encodeURIComponent(customerId!)}/features`),
    ])
    if (sequence !== requestSequence) return
    if (scheduleResult.pagination.total > 0 && scheduleResult.pagination.page > scheduleResult.pagination.totalPages) {
      pagination.value = { ...scheduleResult.pagination, page: scheduleResult.pagination.totalPages }
      await load()
      return
    }
    schedules.value = scheduleResult.items
    pagination.value = scheduleResult.pagination
    features.value = featureResult.items
  } catch (reason) { if (sequence === requestSequence) error.value = readable(reason, '定时任务加载失败') }
  finally { if (sequence === requestSequence) loading.value = false }
}

function openCreate(): void {
  const feature = features.value[0]
  if (!feature) return
  editingId.value = null
  editingCustomerId.value = session.currentCustomerId
  form.value = {
    name: `${feature.name} 定时同步`, customerFeatureId: feature.id,
    mode: 'DAILY', time: '09:00', weekday: 1, monthday: 1,
    cronExpression: '0 9 * * *', isEnabled: true,
  }
  modalOpen.value = true
}

function openEdit(item: Schedule): void {
  const parsed = parseCron(item.cronExpression)
  editingId.value = item.id
  editingCustomerId.value = item.customerId
  form.value = {
    name: item.name,
    customerFeatureId: item.customerFeatureId,
    mode: parsed.mode,
    time: parsed.time,
    weekday: parsed.weekday,
    monthday: parsed.monthday,
    cronExpression: item.cronExpression,
    isEnabled: item.isEnabled,
  }
  modalOpen.value = true
}

async function save(): Promise<void> {
  const customerId = editingId.value ? editingCustomerId.value : session.currentCustomerId
  if (!customerId) return
  busy.value = true
  const wasEditing = Boolean(editingId.value)
  error.value = ''
  try {
    const payload = {
      customerId,
      customerFeatureId: form.value.customerFeatureId,
      name: form.value.name,
      cronExpression: buildCron(),
      isEnabled: form.value.isEnabled,
    }
    if (editingId.value) {
      await apiRequest(`/api/schedules/${editingId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
    } else {
      await apiRequest('/api/schedules', { method: 'POST', body: JSON.stringify(payload) })
    }
    modalOpen.value = false
    await load()
    notify.success(wasEditing ? '定时任务已更新' : '定时任务已创建', { description: form.value.name })
  } catch (reason) {
    error.value = readable(reason, '定时任务保存失败')
    notify.error('定时任务保存失败', { description: error.value })
  }
  finally { busy.value = false }
}
function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }

async function remove(item: Schedule): Promise<void> {
  if (!window.confirm(`确定删除“${item.name}”吗？这不会删除已经产生的运行记录。`)) return
  busy.value = true
  try {
    await apiRequest(`/api/schedules/${item.id}`, { method: 'DELETE' })
    await load()
    notify.success('定时任务已删除', { description: item.name })
  } catch (reason) {
    error.value = readable(reason, '定时任务删除失败')
    notify.error('定时任务删除失败', { description: error.value })
  }
  finally { busy.value = false }
}

function buildCron(): string {
  if (form.value.mode === 'CRON') return form.value.cronExpression.trim()
  const [hourText = '0', minuteText = '0'] = form.value.time.split(':')
  const hour = Number(hourText)
  const minute = Number(minuteText)
  if (form.value.mode === 'WEEKLY') return `${minute} ${hour} * * ${form.value.weekday}`
  if (form.value.mode === 'MONTHLY') return `${minute} ${hour} ${form.value.monthday} * *`
  return `${minute} ${hour} * * *`
}

function parseCron(expression: string): { mode: ScheduleMode; time: string; weekday: number; monthday: number } {
  let match = /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec(expression)
  if (match) return { mode: 'DAILY', time: clock(match[2]!, match[1]!), weekday: 1, monthday: 1 }
  match = /^(\d{1,2}) (\d{1,2}) \* \* ([0-6])$/.exec(expression)
  if (match) return { mode: 'WEEKLY', time: clock(match[2]!, match[1]!), weekday: Number(match[3]), monthday: 1 }
  match = /^(\d{1,2}) (\d{1,2}) ([1-9]|[12]\d|3[01]) \* \*$/.exec(expression)
  if (match) return { mode: 'MONTHLY', time: clock(match[2]!, match[1]!), weekday: 1, monthday: Number(match[3]) }
  return { mode: 'CRON', time: '09:00', weekday: 1, monthday: 1 }
}

function clock(hour: string, minute: string): string {
  return `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
}

function formatTime(value: number | null, timezoneName?: string): string {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      dateStyle: 'medium', timeStyle: 'medium', timeZone: timezoneName,
    }).format(value * 1000)
  } catch { return new Date(value * 1000).toLocaleString('zh-CN') }
}

function outcomeClass(outcome: ScheduleOutcome | null): string {
  if (outcome === 'ENQUEUED' || outcome === 'DUPLICATE') return 'status-pill--on'
  if (outcome === 'MISSED' || outcome === 'QUEUE_FULL') return 'status-pill--danger'
  return 'status-pill--warn'
}

function readable(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback
}
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h1>定时任务</h1><p>Scheduler 到点只创建一次运行请求，脚本仍由 Runner 执行。系统离线期间的时点不会补跑。</p></div>
      <button class="primary-button" type="button" :disabled="loading || session.isAllCustomers || features.length === 0" :title="session.isAllCustomers ? '请先选择一个具体客户' : undefined" @click="openCreate">新建定时任务</button>
    </div>
    <div class="metric-grid">
      <article class="metric-card metric-card--primary"><span>当前页已启用</span><strong>{{ activeCount }}</strong><p>共 {{ pagination.total }} 个定时任务</p></article>
      <article class="metric-card"><span>执行时区</span><strong class="metric-card__name">{{ timezone }}</strong><p>修改系统时区后统一重算下次执行时间</p></article>
      <article class="metric-card"><span>防重复依据</span><strong class="metric-card__name">计划时点</strong><p>同一定时任务与计划时点只会入队一次</p></article>
    </div>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <div v-if="loading" class="content-card loading-state">正在读取定时任务…</div>
    <article v-else-if="!session.isAllCustomers && features.length === 0" class="content-card empty-state-card"><div class="empty-icon">◷</div><h2>当前客户还没有功能</h2><p>请先由管理员注册或复制功能，再设置运行周期。</p></article>
    <article v-else-if="schedules.length === 0" class="content-card empty-state-card"><div class="empty-icon">◷</div><h2>还没有定时任务</h2><p>日常周期可以直接选择每天、每周或每月；复杂周期再使用 Cron。</p></article>
    <article v-else class="content-card table-card"><div class="table-scroll"><table><thead><tr><th v-if="session.isAllCustomers">客户</th><th>任务</th><th>周期</th><th>下次执行</th><th>最近处理</th><th>状态</th><th class="align-right">操作</th></tr></thead><tbody>
      <tr v-for="item in schedules" :key="item.id">
        <td v-if="session.isAllCustomers"><span class="customer-badge">{{ item.customerName }}</span></td>
        <td><strong>{{ item.name }}</strong><small class="block-copy">{{ item.featureName }}</small></td>
        <td><span class="mono-cell">{{ item.cronExpression }}</span><small class="block-copy">{{ item.timezone }}</small></td>
        <td class="nowrap">{{ item.isEnabled ? formatTime(item.nextRunAt, item.timezone) : '已停用' }}</td>
        <td><template v-if="item.lastOutcome"><span class="status-pill" :class="outcomeClass(item.lastOutcome)">{{ outcomeCopy[item.lastOutcome] }}</span><small class="block-copy">{{ item.lastMessage }}</small><RouterLink v-if="item.lastRunRequestId" class="text-link block-copy" :to="`/runs/${item.lastRunRequestId}`">查看本次运行</RouterLink></template><span v-else>—</span></td>
        <td><span class="status-pill" :class="item.isEnabled ? 'status-pill--on' : 'status-pill--off'">{{ item.isEnabled ? '启用' : '停用' }}</span><small v-if="item.missedCount" class="block-copy">累计错过 {{ item.missedCount }} 次</small></td>
        <td class="align-right"><div class="table-actions"><button class="text-button" type="button" @click="openEdit(item)">编辑</button><button class="text-button text-button--danger" type="button" :disabled="busy" @click="remove(item)">删除</button></div></td>
      </tr>
    </tbody></table></div></article>
    <PaginationBar v-if="pagination.total > 0" :pagination="pagination" :disabled="loading" @change="changePage" />

    <ModalDialog :open="modalOpen" :title="editingId ? '编辑定时任务' : '新建定时任务'" description="时间按系统时区计算；停用后不会创建新的运行请求。" width="large" :closeable="!busy" @close="modalOpen = false">
      <form id="schedule-form" class="form-grid" @submit.prevent="save">
        <label class="field"><span>任务名称</span><input v-model="form.name" maxlength="120" required /></label>
        <label class="field"><span>运行功能</span><select v-model="form.customerFeatureId" :disabled="Boolean(editingId)" required><option v-if="editingId" :value="form.customerFeatureId">{{ schedules.find((item) => item.id === editingId)?.featureName ?? '当前功能' }}</option><option v-for="feature in features" :key="feature.id" :value="feature.id">{{ feature.name }} · {{ feature.status }}</option></select><small v-if="editingId">已创建的定时任务不更换功能，避免历史含义变化。</small></label>
        <label class="field"><span>周期类型</span><select v-model="form.mode"><option value="DAILY">每天</option><option value="WEEKLY">每周</option><option value="MONTHLY">每月</option><option value="CRON">高级 Cron</option></select></label>
        <label v-if="form.mode !== 'CRON'" class="field"><span>执行时间</span><input v-model="form.time" type="time" required /></label>
        <label v-if="form.mode === 'WEEKLY'" class="field"><span>星期</span><select v-model.number="form.weekday"><option :value="1">星期一</option><option :value="2">星期二</option><option :value="3">星期三</option><option :value="4">星期四</option><option :value="5">星期五</option><option :value="6">星期六</option><option :value="0">星期日</option></select></label>
        <label v-if="form.mode === 'MONTHLY'" class="field"><span>每月日期</span><input v-model.number="form.monthday" type="number" min="1" max="31" required /><small>没有该日期的月份会自然跳过。</small></label>
        <label v-if="form.mode === 'CRON'" class="field field--wide"><span>5 段 Cron</span><input v-model="form.cronExpression" class="mono-cell" maxlength="120" placeholder="0 9 * * 1-5" required /><small>依次是分钟、小时、日、月、星期；不接受秒字段。</small></label>
        <label class="field field--wide toggle-field"><span><strong>立即启用</strong><small>关闭时保留配置，但不产生运行请求。</small></span><input v-model="form.isEnabled" class="switch" type="checkbox" /></label>
      </form>
      <template #footer><button class="secondary-button" type="button" :disabled="busy" @click="modalOpen = false">取消</button><button class="primary-button" type="submit" form="schedule-form" :disabled="busy">{{ busy ? '正在保存…' : '保存' }}</button></template>
    </ModalDialog>
  </section>
</template>
