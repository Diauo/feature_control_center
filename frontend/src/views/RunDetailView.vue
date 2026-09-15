<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest, downloadFile } from '@/lib/api'
import { notify } from '@/lib/notify'
import { MAX_VISIBLE_RUN_EVENTS, RunEventBuffer } from '@/lib/runEventBuffer'
import type { Paginated, Pagination, RunEvent, RunReportItem, RunReportItemStatus, RunReportSummary, RunStatus, RunSummary } from '@/types'

const route = useRoute()
const router = useRouter()
const requestId = String(route.params.requestId)
const run = ref<RunSummary | null>(null)
const events = ref<RunEvent[]>([])
const loading = ref(true)
const stopping = ref(false)
const error = ref('')
const connection = ref<'connecting' | 'live' | 'reconnecting' | 'closed'>('connecting')
const autoScroll = ref(true)
const logPanel = ref<HTMLElement | null>(null)
const omittedEventCount = ref(0)
const report = ref<RunReportSummary | null>(null)
const reportItems = ref<RunReportItem[]>([])
const reportLoading = ref(false)
const reportError = ref('')
const reportStatusFilter = ref('')
const reportPagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const activePanel = ref<'report' | 'logs'>('logs')
const eventBuffer = new RunEventBuffer()
const queuedEvents: RunEvent[] = []
let stream: EventSource | null = null
let eventFlushTimer: number | null = null
let scrollFrame: number | null = null

const terminal = computed(() => run.value ? ['SUCCEEDED', 'FAILED', 'STOPPED', 'TIMED_OUT', 'INTERRUPTED'].includes(run.value.status) : false)
const logsPurged = computed(() => run.value?.logsPurgedAt != null)
const canStop = computed(() => run.value ? ['QUEUED', 'STARTING', 'RUNNING', 'STOPPING'].includes(run.value.status) && run.value.status !== 'STOPPING' : false)
const statusCopy: Record<RunStatus, string> = {
  QUEUED: '排队中', STARTING: '正在启动', RUNNING: '运行中', STOPPING: '停止中',
  SUCCEEDED: '已完成', FAILED: '执行失败', STOPPED: '已停止', TIMED_OUT: '已超时', INTERRUPTED: '已中断',
}
const connectionCopy = computed(() => logsPurged.value ? '日志已清理' : ({ connecting: '连接中', live: '实时连接', reconnecting: '正在重连', closed: '日志已封存' })[connection.value])
const reportStatusCopy = { OPEN: '生成中', COMPLETE: '完整', INCOMPLETE: '未完整' } as const
const reportItemStatusCopy: Record<RunReportItemStatus, string> = {
  SUCCESS: '成功', FAILED: '失败', NO_DATA: '无数据', SKIPPED: '已跳过', UNFINISHED: '未完成',
}

onMounted(load)
watch(autoScroll, (enabled) => { if (enabled) scheduleScroll() })
onBeforeUnmount(dispose)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const runResult = await apiRequest<{ run: RunSummary }>(`/api/runs/${requestId}`)
    run.value = runResult.run
    await loadReport()
    if (terminal.value && report.value) activePanel.value = 'report'
    const startAfter = Math.max(0, runResult.run.latestSequence - MAX_VISIBLE_RUN_EVENTS)
    eventBuffer.reset(startAfter)
    omittedEventCount.value = startAfter
    const eventResult = await apiRequest<{ items: RunEvent[] }>(
      `/api/runs/${requestId}/events?after=${startAfter}&limit=500`,
    )
    appendEvents(eventResult.items)
    if (logsPurged.value || (terminal.value && eventBuffer.cursor >= runResult.run.latestSequence)) {
      connection.value = 'closed'
    } else {
      openStream()
    }
  } catch (reason) { error.value = readable(reason, '任务详情加载失败') }
  finally { loading.value = false }
}

function openStream(): void {
  closeStream()
  const cursor = eventBuffer.cursor
  connection.value = 'connecting'
  stream = new EventSource(`/api/runs/${requestId}/events/stream?after=${cursor}`)
  stream.addEventListener('open', () => { connection.value = 'live' })
  stream.addEventListener('log', (raw) => {
    try { queueEvent(JSON.parse((raw as MessageEvent).data) as RunEvent) }
    catch { error.value = '收到格式无效的实时日志事件' }
  })
  stream.addEventListener('run', (raw) => {
    try {
      flushQueuedEvents()
      const update = JSON.parse((raw as MessageEvent).data) as { status: RunStatus; latestSequence: number; logsPurgedAt?: number | null }
      if (run.value) {
        run.value.status = update.status
        run.value.latestSequence = update.latestSequence
        if (update.logsPurgedAt != null) run.value.logsPurgedAt = update.logsPurgedAt
      }
      connection.value = 'closed'
      closeStream()
      void finishLiveRun()
    } catch {
      error.value = '收到格式无效的任务状态事件'
    }
  })
  stream.addEventListener('auth', () => {
    closeStream()
    window.dispatchEvent(new CustomEvent('fcc:auth-expired'))
  })
  stream.onerror = () => {
    if (!terminal.value) connection.value = 'reconnecting'
  }
}

function closeStream(): void {
  stream?.close()
  stream = null
}

function appendEvents(incoming: RunEvent[]): void {
  const result = eventBuffer.append(events.value, incoming)
  omittedEventCount.value = result.omitted
  if (run.value && result.cursor > run.value.latestSequence) run.value.latestSequence = result.cursor
  if (result.added > 0) scheduleScroll()
}

function queueEvent(event: RunEvent): void {
  queuedEvents.push(event)
  if (eventFlushTimer !== null) return
  eventFlushTimer = window.setTimeout(() => {
    eventFlushTimer = null
    flushQueuedEvents()
  }, 50)
}

function flushQueuedEvents(): void {
  if (eventFlushTimer !== null) {
    window.clearTimeout(eventFlushTimer)
    eventFlushTimer = null
  }
  if (queuedEvents.length === 0) return
  appendEvents(queuedEvents.splice(0, queuedEvents.length))
}

function scheduleScroll(): void {
  if (!autoScroll.value || scrollFrame !== null) return
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = null
    if (autoScroll.value && logPanel.value) logPanel.value.scrollTop = logPanel.value.scrollHeight
  })
}

function dispose(): void {
  closeStream()
  queuedEvents.length = 0
  if (eventFlushTimer !== null) window.clearTimeout(eventFlushTimer)
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
  eventFlushTimer = null
  scrollFrame = null
}

async function refreshRun(): Promise<void> {
  try { run.value = (await apiRequest<{ run: RunSummary }>(`/api/runs/${requestId}`)).run }
  catch (reason) { error.value = readable(reason, '任务状态刷新失败') }
}

async function finishLiveRun(): Promise<void> {
  await refreshRun()
  reportPagination.value.page = 1
  await loadReport()
  if (report.value) activePanel.value = 'report'
}

async function loadReport(): Promise<void> {
  reportLoading.value = true
  reportError.value = ''
  try {
    report.value = (await apiRequest<{ report: RunReportSummary | null }>(`/api/runs/${requestId}/report`)).report
    if (!report.value || report.value.detailsPurgedAt) {
      reportItems.value = []
      reportPagination.value = { ...reportPagination.value, total: 0, totalPages: 1 }
      return
    }
    const query = new URLSearchParams({
      page: String(reportPagination.value.page),
      pageSize: String(reportPagination.value.pageSize),
    })
    if (reportStatusFilter.value) query.set('status', reportStatusFilter.value)
    const result = await apiRequest<Paginated<RunReportItem>>(`/api/runs/${requestId}/report/items?${query}`)
    reportItems.value = result.items
    reportPagination.value = result.pagination
  } catch (reason) {
    reportError.value = readable(reason, '最终报表加载失败')
  } finally {
    reportLoading.value = false
  }
}

function applyReportFilter(): void {
  reportPagination.value.page = 1
  void loadReport()
}

function changeReportPage(page: number, pageSize: number): void {
  reportPagination.value = { ...reportPagination.value, page, pageSize }
  void loadReport()
}

async function downloadReport(): Promise<void> {
  if (!terminal.value || !report.value || report.value.detailsPurgedAt) return
  reportError.value = ''
  try {
    await downloadFile(`/api/runs/${requestId}/report.xlsx`)
    notify.success('XLSX 报表已开始下载', { description: '文件包含执行汇总和结果明细两个工作表。' })
  } catch (reason) {
    reportError.value = readable(reason, 'XLSX 报表下载失败')
    notify.error('XLSX 报表下载失败', { description: reportError.value })
  }
}

async function stop(): Promise<void> {
  if (!canStop.value || stopping.value) return
  stopping.value = true
  error.value = ''
  try {
    run.value = (await apiRequest<{ run: RunSummary }>(`/api/runs/${requestId}/stop`, { method: 'POST' })).run
    notify.warning('停止请求已提交', { description: 'Runner 会先尝试正常终止，超过宽限期后强制停止。' })
  } catch (reason) {
    error.value = readable(reason, '停止请求提交失败')
    notify.error('停止请求提交失败', { description: error.value })
  }
  finally { stopping.value = false }
}

async function downloadLog(format: 'log' | 'jsonl'): Promise<void> {
  if (logsPurged.value) return
  error.value = ''
  try {
    await downloadFile(`/api/runs/${requestId}/log.${format}`)
    notify.success('任务日志已开始下载', { description: format.toUpperCase() })
  }
  catch (reason) {
    if (reason instanceof ApiError && reason.code === 'RUN_LOGS_PURGED') await refreshRun()
    error.value = readable(reason, '日志下载失败')
    notify.error('任务日志下载失败', { description: error.value })
  }
}

function formatTime(value: number | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(value * 1000)
}
function formatEventTime(value: number): string {
  const date = new Date(value)
  return `${date.toLocaleTimeString('zh-CN', { hour12: false })}.${String(date.getMilliseconds()).padStart(3, '0')}`
}
function hasContext(context: Record<string, unknown>): boolean { return Object.keys(context).length > 0 }
function formatReportValue(value: string | number | boolean | null | undefined): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}
function readable(reason: unknown, fallback: string): string { return reason instanceof ApiError ? reason.message : fallback }
</script>

<template>
  <section>
    <div class="page-heading run-heading"><div><h1>{{ run?.featureName ?? '任务详情' }}</h1><p class="mono-cell">{{ requestId }}</p></div><div class="run-heading__actions"><button class="secondary-button" type="button" @click="router.push('/runs')">返回记录</button><button v-if="canStop" class="danger-button" type="button" :disabled="stopping" @click="stop">{{ stopping ? '正在提交…' : '停止任务' }}</button></div></div>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <div v-if="loading" class="content-card loading-state">正在连接任务日志…</div>
    <template v-else-if="run">
      <div class="run-summary-grid">
        <article class="content-card run-summary"><span>状态</span><strong>{{ statusCopy[run.status] }}</strong><small>{{ connectionCopy }}</small></article>
        <article class="content-card run-summary"><span>进入队列</span><strong>{{ formatTime(run.queuedAt) }}</strong><small>代码版本 {{ run.versionNumber }} · {{ run.triggerSource === 'MANUAL' ? '手动运行' : '定时运行' }}</small></article>
        <article class="content-card run-summary"><span>数据源快照</span><strong>{{ run.dataSourceFilename ?? '不使用数据源' }}</strong><small>{{ run.dataSourceRevisionId ? `修订 ${run.dataSourceRevisionId.slice(0, 8)}` : '—' }}</small></article>
      </div>
      <div class="section-tabs run-section-tabs" role="tablist" aria-label="运行详情内容">
        <button type="button" :class="{ active: activePanel === 'report' }" role="tab" :aria-selected="activePanel === 'report'" @click="activePanel = 'report'"><span class="section-tabs__label">最终报表<small v-if="report">{{ report.reportedTotal }}</small></span></button>
        <button type="button" :class="{ active: activePanel === 'logs' }" role="tab" :aria-selected="activePanel === 'logs'" @click="activePanel = 'logs'"><span class="section-tabs__label">实时日志<small>{{ events.length }}</small></span></button>
      </div>
      <Transition name="section-fade" mode="out-in">
        <div v-if="activePanel === 'report'" key="report" class="run-panel">
          <p v-if="reportError" class="form-error page-error">{{ reportError }}</p>
          <article v-if="reportLoading" class="content-card loading-state">正在读取最终报表…</article>
          <article v-else-if="!report" class="content-card empty-state-card"><div class="empty-icon">≡</div><h2>这个功能没有提交结构化报表</h2><p>旧功能仍可正常运行，请切换到“实时日志”查看执行过程。新功能可通过 <code>ctx.report</code> 提交通用业务结果。</p></article>
          <template v-else>
            <article class="content-card report-overview">
              <header class="report-toolbar"><div><span class="report-eyebrow">{{ report.itemLabel }}报表</span><h2>{{ report.title }}</h2><p>报表{{ reportStatusCopy[report.status] }} · 已形成 {{ report.reportedTotal }} 条明细<span v-if="report.expectedTotal != null"> / 预计 {{ report.expectedTotal }} 条</span></p></div><button class="secondary-button" type="button" :disabled="!terminal || Boolean(report.detailsPurgedAt)" @click="downloadReport">导出 XLSX</button></header>
              <div class="report-metrics">
                <div><span>总数</span><strong>{{ report.total }}</strong></div>
                <div class="report-metric--success"><span>成功</span><strong>{{ report.successCount }}</strong></div>
                <div class="report-metric--failed"><span>失败</span><strong>{{ report.failedCount }}</strong></div>
                <div><span>无数据</span><strong>{{ report.noDataCount }}</strong></div>
                <div><span>已跳过</span><strong>{{ report.skippedCount }}</strong></div>
                <div :class="{ 'report-metric--failed': report.unfinishedCount > 0 }"><span>未完成</span><strong>{{ report.unfinishedCount }}</strong></div>
              </div>
            </article>
            <div v-if="report.status === 'INCOMPLETE'" class="info-card info-card--warning"><span class="info-symbol">!</span><div><strong>报表未完整封存</strong><p>任务可能被停止、超时或中断。已提交的明细仍然保留<span v-if="report.unreportedCount > 0">，另有 {{ report.unreportedCount }} 条预计数据没有形成明细</span>。</p></div></div>
            <div v-if="report.validationErrorCount > 0" class="info-card info-card--warning"><span class="info-symbol">!</span><div><strong>部分报表数据不符合功能声明</strong><p>Runner 拒绝了 {{ report.validationErrorCount }} 条无效指令，请由功能开发人员检查运行日志。</p></div></div>
            <div v-if="report.detailsPurgedAt" class="info-card"><span class="info-symbol">i</span><div><strong>报表明细已自动清理</strong><p>清理时间为 {{ formatTime(report.detailsPurgedAt) }}。汇总数字仍然保留，但明细和 Excel 已不可下载。</p></div></div>
            <article v-else class="content-card report-detail-card">
              <header class="report-detail-toolbar"><div><h2>结果明细</h2><p>状态由业务脚本判定，平台只负责保存和中文展示。</p></div><label class="field report-status-filter"><span>状态</span><select v-model="reportStatusFilter" @change="applyReportFilter"><option value="">全部状态</option><option v-for="(label, value) in reportItemStatusCopy" :key="value" :value="value">{{ label }}</option></select></label></header>
              <div v-if="reportItems.length === 0" class="empty-table">{{ reportStatusFilter ? '没有符合当前状态的明细' : '报表没有明细数据' }}</div>
              <div v-else class="table-scroll"><table><thead><tr><th>序号</th><th v-for="column in report.columns" :key="column.key">{{ column.label }}</th><th>状态</th><th>原因</th><th>完成时间</th></tr></thead><tbody><tr v-for="item in reportItems" :key="item.sequence"><td>{{ item.sequence }}</td><td v-for="column in report.columns" :key="column.key">{{ formatReportValue(item.values[column.key]) }}</td><td><span class="status-pill" :class="item.status === 'SUCCESS' ? 'status-pill--on' : ['FAILED', 'UNFINISHED'].includes(item.status) ? 'status-pill--danger' : 'status-pill--warn'">{{ reportItemStatusCopy[item.status] }}</span></td><td class="report-reason">{{ item.reason || '—' }}</td><td class="nowrap">{{ formatEventTime(item.reportedAtMs) }}</td></tr></tbody></table></div>
            </article>
            <PaginationBar v-if="!report.detailsPurgedAt && reportPagination.total > 20" :pagination="reportPagination" :disabled="reportLoading" @change="changeReportPage" />
          </template>
        </div>
        <div v-else key="logs" class="run-panel">
          <article class="content-card console-card">
            <header class="console-toolbar"><div><span class="connection-dot" :class="`connection-dot--${connection}`"></span><strong>实时日志</strong><small>显示 {{ events.length }} 条<span v-if="omittedEventCount > 0"> · 已省略 {{ omittedEventCount }} 条</span> · 序号 {{ eventBuffer.cursor }}</small></div><div class="console-actions"><label><input v-model="autoScroll" type="checkbox" :disabled="logsPurged" /> 自动滚动</label><button class="text-button" type="button" :disabled="logsPurged" @click="downloadLog('log')">下载 .log</button><button class="text-button" type="button" :disabled="logsPurged" @click="downloadLog('jsonl')">下载 .jsonl</button></div></header>
            <p v-if="omittedEventCount > 0 && !logsPurged" class="console-limit-notice">为保持页面流畅，这里只显示最近 {{ MAX_VISIBLE_RUN_EVENTS }} 条日志；完整日志仍可下载。</p>
            <div ref="logPanel" class="log-console" role="log" :aria-live="terminal ? 'off' : 'polite'" aria-label="任务实时日志">
              <div v-if="logsPurged" class="log-empty">日志已按系统保留策略自动清理，任务摘要仍然保留。</div>
              <div v-else-if="events.length === 0" class="log-empty">等待 Runner 输出日志…</div>
              <div v-for="event in events" :key="event.sequence" class="log-line" :class="`log-line--${event.level.toLowerCase()}`"><span class="log-sequence">{{ String(event.sequence).padStart(4, '0') }}</span><time>{{ formatEventTime(event.occurredAtMs) }}</time><span class="log-source">{{ event.source }}</span><span class="log-message">{{ event.message }}<details v-if="hasContext(event.context)" class="log-context"><summary>技术字段</summary><code>{{ JSON.stringify(event.context) }}</code></details></span></div>
            </div>
          </article>
          <div v-if="logsPurged" class="info-card"><span class="info-symbol">i</span><div><strong>日志已自动清理</strong><p>清理时间为 {{ formatTime(run.logsPurgedAt) }}。任务状态和执行摘要仍然保留，但日志内容已不可下载。</p></div></div>
          <div v-else-if="terminal" class="info-card"><span class="info-symbol">✓</span><div><strong>日志已封存</strong><p>最终状态为 {{ statusCopy[run.status] }}。下载文件由数据库中的同一组日志事件即时生成，不存在第二份不一致的“最终日志”。</p></div></div>
        </div>
      </Transition>
    </template>
  </section>
</template>
