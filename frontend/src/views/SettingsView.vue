<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ModalDialog from '@/components/ModalDialog.vue'
import AnimatedTabs from '@/components/AnimatedTabs.vue'
import SearchCombobox from '@/components/SearchCombobox.vue'
import SettingsSection from '@/components/SettingsSection.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest, downloadFile } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { Paginated, Pagination } from '@/types'

type SettingsTab = 'status' | 'settings' | 'logs' | 'updates' | 'releases'
type ReauthAction = 'settings' | 'apply' | 'retry' | 'rollback'
interface ServiceStatus { name: string; status: 'ACTIVE' | 'OFFLINE'; heartbeatAt: number | null; startedAt: number | null; processId?: number }
interface PlatformStatus { version: string; serverTime: number; configuredTimezone: string; activeRuns: number; services: ServiceStatus[] }
interface SystemLogEntry { timestamp: string; service: string; level: string; logger: string; message: string; requestId?: string; exception?: string }
interface ReleaseEntry { version: string; date: string; title: string; items: string[] }
interface UpdateItem {
  id: string
  operation: 'APPLY' | 'ROLLBACK'
  sourceVersion: string
  targetVersion: string
  packageFilename: string | null
  packageSha256: string | null
  packageSize: number | null
  releaseNotes: string[]
  status: 'READY' | 'PENDING' | 'APPLYING' | 'SUCCEEDED' | 'FAILED' | 'ROLLED_BACK'
  stage: string
  progress: number
  rollbackCompatible: boolean
  backupFilename: string | null
  errorMessage: string | null
  actorDisplayName: string | null
  clientIp: string | null
  createdAt: number
  updatedAt: number
  completedAt: number | null
  canApply: boolean
  canRetry: boolean
}
interface UpdateOverview {
  currentVersion: string
  runtimePlatform: string
  supervisor: { available: boolean; heartbeatAt: number | null; protocol: number | null; processId: number | null; managedVersion: string | null }
  activeRuns: number
  updateInProgress: boolean
  canRollback: boolean
  rollbackTargetVersion: string | null
  items: UpdateItem[]
  pagination: Pagination
}

const session = useSessionStore()
const activeTab = ref<SettingsTab>('status')
const openSections = ref(new Set<string>(['identity']))
const values = ref<Record<string, any>>({})
const proxyCidrs = ref('')
const managementCidrs = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const reauthOpen = ref(false)
const reauthAction = ref<ReauthAction>('settings')
const reauthUpdateId = ref('')
const password = ref('')
const reauthError = ref('')
const status = ref<PlatformStatus | null>(null)
const timezones = ref<string[]>([])
const serverTimezone = ref('UTC')
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const releaseItems = ref<ReleaseEntry[]>([])
const systemLogMaxMiB = ref(0)
const updateMaxMiB = ref(500)
const logService = ref('all')
const logDate = ref(new Date().toISOString().slice(0, 10))
const logLevel = ref('')
const logEntries = ref<SystemLogEntry[]>([])
const logCursor = ref('')
const logLoading = ref(false)
const updateOverview = ref<UpdateOverview | null>(null)
const updateLoading = ref(false)
const updateUploadBusy = ref(false)
const updateConnectionError = ref('')
const updateFileInput = ref<HTMLInputElement | null>(null)
const updatePagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const releasePagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const knownUpdateStatuses = new Map<string, string>()
let statusTimer: number | undefined
let logTimer: number | undefined
let updateTimer: number | undefined

const timezoneOptions = computed(() => timezones.value.map((value) => ({
  value,
  label: value,
  description: value === browserTimezone ? '当前浏览器' : value === serverTimezone.value ? '服务器检测' : undefined,
})))
const formatOptions = [
  { id: 'zip', label: 'ZIP', extensions: '.zip' },
  { id: '7z', label: '7z', extensions: '.7z' },
  { id: 'rar', label: 'RAR', extensions: '.rar' },
  { id: 'tar', label: 'TAR', extensions: '.tar' },
  { id: 'tar_gz', label: 'TAR + Gzip', extensions: '.tar.gz / .tgz' },
  { id: 'tar_bz2', label: 'TAR + Bzip2', extensions: '.tar.bz2 / .tbz2' },
  { id: 'tar_xz', label: 'TAR + XZ', extensions: '.tar.xz / .txz' },
]
const settingTabs = [
  { value: 'status', label: '运行状态' }, { value: 'settings', label: '系统参数' },
  { value: 'logs', label: '程序日志' }, { value: 'updates', label: '系统更新' },
  { value: 'releases', label: '更新记录' },
]

function toggleSection(id: string): void {
  const next = new Set(openSections.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  openSections.value = next
}
function selectSettingsTab(value: string): void {
  if (['status', 'settings', 'logs', 'updates', 'releases'].includes(value)) activeTab.value = value as SettingsTab
}
function changeUpdatePage(page: number, pageSize: number): void { updatePagination.value = { ...updatePagination.value, page, pageSize }; void loadUpdates() }
function changeReleasePage(page: number, pageSize: number): void { releasePagination.value = { ...releasePagination.value, page, pageSize }; void loadReleases() }

onMounted(async () => {
  await Promise.all([load(), loadStatus(), loadTimezones(), loadReleases()])
  startPolling()
  document.addEventListener('visibilitychange', startPolling)
})
onBeforeUnmount(() => {
  window.clearInterval(statusTimer)
  window.clearInterval(logTimer)
  window.clearInterval(updateTimer)
  document.removeEventListener('visibilitychange', startPolling)
})

watch(activeTab, () => startPolling())
watch([logService, logDate, logLevel], () => {
  logCursor.value = ''
  logEntries.value = []
  if (activeTab.value === 'logs') void loadLogs(false)
})

function startPolling(): void {
  window.clearInterval(statusTimer)
  window.clearInterval(logTimer)
  window.clearInterval(updateTimer)
  if (document.hidden) return
  if (activeTab.value === 'status') {
    void loadStatus()
    statusTimer = window.setInterval(loadStatus, 5000)
  }
  if (activeTab.value === 'logs') {
    void loadLogs(logCursor.value !== '')
    logTimer = window.setInterval(() => loadLogs(true), 3000)
  }
  if (activeTab.value === 'updates') {
    void loadUpdates()
    updateTimer = window.setInterval(loadUpdates, 2000)
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await apiRequest<{ values: Record<string, unknown> }>('/api/admin/settings')
    values.value = result.values
    session.systemName = String(result.values['system.name'] ?? session.systemName)
    proxyCidrs.value = stringList(result.values['security.trusted_proxy_cidrs']).join('\n')
    managementCidrs.value = stringList(result.values['security.management_trusted_cidrs']).join('\n')
    systemLogMaxMiB.value = Math.round(Number(result.values['system_logs.max_total_bytes'] ?? 0) / 1024 / 1024)
    updateMaxMiB.value = Math.round(Number(result.values['updates.max_package_bytes'] ?? 524_288_000) / 1024 / 1024)
  } catch (reason) { error.value = readable(reason, '系统设置加载失败') }
  finally { loading.value = false }
}

async function loadUpdates(): Promise<void> {
  if (updateLoading.value) return
  updateLoading.value = true
  try {
    const result = await apiRequest<UpdateOverview>(`/api/admin/system/updates?page=${updatePagination.value.page}&pageSize=${updatePagination.value.pageSize}`)
    const hadSnapshot = knownUpdateStatuses.size > 0
    if (hadSnapshot) {
      for (const item of result.items) {
        const previous = knownUpdateStatuses.get(item.id)
        if (previous && previous !== item.status && item.status === 'SUCCEEDED') {
          notify.success(item.operation === 'ROLLBACK' ? '系统回退完成' : '系统更新完成', {
            description: `当前版本 ${result.currentVersion}`,
            duration: 12_000,
            action: { label: '刷新页面', onClick: () => window.location.reload() },
          })
        } else if (previous && previous !== item.status && (item.status === 'FAILED' || item.status === 'ROLLED_BACK')) {
          notify.error(
            item.status === 'ROLLED_BACK'
              ? '系统更新失败，已自动恢复'
              : item.operation === 'ROLLBACK' ? '系统回退失败' : '系统更新失败',
            {
              description: item.errorMessage ?? '请查看更新记录',
              duration: 12_000,
            },
          )
        }
      }
    }
    knownUpdateStatuses.clear()
    result.items.forEach((item) => knownUpdateStatuses.set(item.id, item.status))
    updateOverview.value = result
    updatePagination.value = result.pagination
    updateConnectionError.value = ''
  } catch (reason) {
    updateConnectionError.value = updateOverview.value
      ? '服务正在切换或暂时不可达，页面会自动重试。'
      : readable(reason, '系统更新状态加载失败')
  } finally { updateLoading.value = false }
}

async function loadStatus(): Promise<void> {
  try { status.value = await apiRequest<PlatformStatus>('/api/admin/system/status') }
  catch (reason) { if (!status.value) error.value = readable(reason, '服务状态加载失败') }
}

async function loadTimezones(): Promise<void> {
  try {
    const result = await apiRequest<{ items: string[]; serverDetected: string }>('/api/admin/system/timezones')
    timezones.value = result.items
    serverTimezone.value = result.serverDetected
  } catch (reason) { error.value = readable(reason, '时区列表加载失败') }
}

async function loadReleases(): Promise<void> {
  try {
    const result = await apiRequest<Paginated<ReleaseEntry>>(`/api/admin/system/release-history?page=${releasePagination.value.page}&pageSize=${releasePagination.value.pageSize}`)
    releaseItems.value = result.items
    releasePagination.value = result.pagination
  }
  catch (reason) { error.value = readable(reason, '更新记录加载失败') }
}

async function loadLogs(incremental: boolean): Promise<void> {
  if (logLoading.value) return
  logLoading.value = true
  try {
    const query = new URLSearchParams({ service: logService.value, date: logDate.value, level: logLevel.value, limit: '300' })
    if (incremental && logCursor.value) query.set('cursor', logCursor.value)
    const result = await apiRequest<{ items: SystemLogEntry[]; cursor: string }>(`/api/admin/system/logs?${query}`)
    logEntries.value = incremental ? [...logEntries.value, ...result.items].slice(-1000) : result.items
    logCursor.value = result.cursor
  } catch (reason) { error.value = readable(reason, '程序日志加载失败') }
  finally { logLoading.value = false }
}

async function save(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const update = { ...values.value }
    delete update['request.client_ip']
    delete update['request.suggested_cidr']
    update['security.trusted_proxy_cidrs'] = lines(proxyCidrs.value)
    update['security.management_trusted_cidrs'] = lines(managementCidrs.value)
    update['system_logs.max_total_bytes'] = Math.max(0, Math.round(systemLogMaxMiB.value * 1024 * 1024))
    update['updates.max_package_bytes'] = Math.max(10, Math.round(updateMaxMiB.value)) * 1024 * 1024
    const result = await apiRequest<{ values: Record<string, unknown> }>('/api/admin/settings', {
      method: 'PUT', body: JSON.stringify({ values: update }),
    })
    values.value = result.values
    session.systemName = String(result.values['system.name'] ?? session.systemName)
    proxyCidrs.value = stringList(result.values['security.trusted_proxy_cidrs']).join('\n')
    managementCidrs.value = stringList(result.values['security.management_trusted_cidrs']).join('\n')
    systemLogMaxMiB.value = Math.round(Number(result.values['system_logs.max_total_bytes'] ?? 0) / 1024 / 1024)
    updateMaxMiB.value = Math.round(Number(result.values['updates.max_package_bytes'] ?? 524_288_000) / 1024 / 1024)
    notify.success('系统设置已保存')
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') {
      openReauth('settings')
    } else {
      error.value = readable(reason, '设置保存失败')
      notify.error('设置保存失败', { description: error.value })
    }
  } finally { busy.value = false }
}

async function confirmReauth(): Promise<void> {
  busy.value = true
  try {
    await session.reauthenticate(password.value)
    reauthOpen.value = false
    busy.value = false
    if (reauthAction.value === 'settings') await save()
    else if (reauthAction.value === 'apply') await applyUpdate(reauthUpdateId.value)
    else if (reauthAction.value === 'retry') await retryUpdate(reauthUpdateId.value)
    else await rollbackUpdate()
  }
  catch (reason) { reauthError.value = readable(reason, '密码验证失败') }
  finally { busy.value = false }
}

function openReauth(action: ReauthAction, updateId = ''): void {
  reauthAction.value = action
  reauthUpdateId.value = updateId
  password.value = ''
  reauthError.value = ''
  reauthOpen.value = true
}

async function uploadUpdatePackage(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const toastId = notify.loading('正在校验更新包', { description: '正在验证签名、版本和文件摘要。' })
  updateUploadBusy.value = true
  updateConnectionError.value = ''
  try {
    const body = new FormData()
    body.append('package', file)
    const result = await apiRequest<{ item: UpdateItem }>('/api/admin/system/updates/packages', { method: 'POST', body })
    notify.dismiss(toastId)
    notify.success('更新包验证通过', { description: `${result.item.sourceVersion} → ${result.item.targetVersion}` })
    updatePagination.value.page = 1
    await loadUpdates()
  } catch (reason) {
    notify.dismiss(toastId)
    const message = readable(reason, '更新包上传失败')
    updateConnectionError.value = message
    notify.error('更新包上传失败', { description: message })
  } finally {
    updateUploadBusy.value = false
    input.value = ''
  }
}

async function retryUpdate(updateId: string): Promise<void> {
  busy.value = true
  try {
    await apiRequest(`/api/admin/system/updates/${encodeURIComponent(updateId)}/retry`, { method: 'POST' })
    updatePagination.value.page = 1
    await loadUpdates()
    notify.success('已创建新的更新尝试', { description: '失败记录会保留，请在新记录上确认安装。' })
  } catch (reason) {
    notify.error('无法重新尝试更新', { description: readable(reason, '更新包不可用') })
  } finally { busy.value = false }
}

async function applyUpdate(updateId: string): Promise<void> {
  if (!updateId || busy.value) return
  busy.value = true
  updateConnectionError.value = ''
  try {
    await apiRequest(`/api/admin/system/updates/${encodeURIComponent(updateId)}/apply`, { method: 'POST' })
    notify.info('更新请求已提交', { description: '服务会短暂重启，本页面将自动恢复连接。' })
    await loadUpdates()
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') openReauth('apply', updateId)
    else {
      const message = readable(reason, '系统更新请求失败')
      updateConnectionError.value = message
      notify.error('无法开始系统更新', { description: message })
    }
  } finally { busy.value = false }
}

async function rollbackUpdate(): Promise<void> {
  if (busy.value) return
  busy.value = true
  updateConnectionError.value = ''
  try {
    await apiRequest('/api/admin/system/updates/rollback', { method: 'POST' })
    notify.warning('回退请求已提交', { description: '数据库数据会保留，服务会短暂重启。' })
    await loadUpdates()
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') openReauth('rollback')
    else {
      const message = readable(reason, '系统回退请求失败')
      updateConnectionError.value = message
      notify.error('无法开始系统回退', { description: message })
    }
  } finally { busy.value = false }
}

async function downloadSystemLog(): Promise<void> {
  if (logService.value === 'all') {
    error.value = '下载前请选择一个具体服务'
    return
  }
  try {
    await downloadFile(`/api/admin/system/logs/download?service=${encodeURIComponent(logService.value)}&date=${encodeURIComponent(logDate.value)}`)
    notify.success('程序日志已开始下载')
  } catch (reason) {
    error.value = readable(reason, '程序日志下载失败')
    notify.error('程序日志下载失败', { description: error.value })
  }
}

function toggleFormat(id: string, checked: boolean): void {
  const current = stringList(values.value['feature.allowed_package_formats'])
  values.value['feature.allowed_package_formats'] = checked
    ? [...new Set([...current, id])]
    : current.filter((item) => item !== id)
}
function addCurrentAddress(): void {
  const suggestion = String(values.value['request.suggested_cidr'] ?? '')
  const current = lines(managementCidrs.value)
  if (suggestion && !current.includes(suggestion)) managementCidrs.value = [...current, suggestion].join('\n')
}
function lines(value: string): string[] { return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean) }
function stringList(value: unknown): string[] { return Array.isArray(value) ? value.map(String) : [] }
function readable(reason: unknown, fallback: string): string { return reason instanceof ApiError ? reason.message : fallback }
function formatTime(value: number | null): string { return value ? new Date(value * 1000).toLocaleString() : '尚无心跳' }
function formatBytes(value: number | null): string {
  if (value === null) return '—'
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KiB`
  return `${(value / 1024 / 1024).toFixed(1)} MiB`
}
function updateStatusLabel(value: UpdateItem['status']): string {
  return ({ READY: '已验证', PENDING: '等待执行', APPLYING: '正在执行', SUCCEEDED: '已完成', FAILED: '失败', ROLLED_BACK: '已自动回退' })[value]
}
function updateStageLabel(value: string): string {
  return ({ VERIFIED: '签名验证完成', QUEUED: '等待启动器接管', VALIDATING: '重新验证更新请求', INSTALLING_RELEASE: '离线安装新版本', BACKING_UP_DATABASE: '备份并检查数据库', DATABASE_PREFLIGHT: '执行迁移与预检', STARTING_CANDIDATE: '启动并检查候选版本', COMPLETED: '执行完成', CONTROL_ERROR: '提交失败', CONTROL_INVALID: '异常控制文件已拒绝', CONTROL_HANDOFF_LOST: '控制交接中断', RECOVERED_AFTER_INTERRUPTION: '中断后已恢复', RECOVERY_FAILED: '自动恢复失败', AUTOMATIC_ROLLBACK: '失败后已自动回退', FAILED_BEFORE_DATABASE_CHANGE: '数据库变更前失败' } as Record<string, string>)[value] ?? value
}
function reauthDescription(): string {
  if (reauthAction.value === 'apply') return '安装更新会重启 Web、Runner 和 Scheduler，并在迁移前备份数据库。'
  if (reauthAction.value === 'rollback') return '回退会切换到上一版本程序，当前数据库数据不会被历史备份覆盖。'
  if (reauthAction.value === 'retry') return '系统会保留失败记录，并基于原签名包创建一次新的安装尝试。'
  return '系统、网络、依赖与任务设置会影响整个平台。'
}
</script>

<template>
  <section>
    <div class="page-heading">
      <div><h1>系统设置</h1><p>状态、参数、程序日志、系统更新与版本信息集中在这里管理。</p></div>
      <button v-if="activeTab === 'settings'" class="primary-button" type="button" :disabled="busy || loading" @click="save">{{ busy ? '正在保存…' : '保存设置' }}</button>
    </div>
    <AnimatedTabs :model-value="activeTab" :options="settingTabs" aria-label="系统设置子功能" @update:model-value="selectSettingsTab" />
    <p v-if="error" class="form-error page-error">{{ error }}</p>

    <Transition name="subpanel" mode="out-in"><div :key="activeTab" class="subpanel-stage">
    <div v-if="activeTab === 'status'" class="settings-stack">
      <div v-if="!status" class="content-card loading-state">正在读取服务状态…</div>
      <template v-else>
        <div class="metric-grid system-metrics">
          <article class="metric-card metric-card--primary"><span>平台版本</span><strong>{{ status.version }}</strong><p>版本和更新记录来自当前交付包</p></article>
          <article class="metric-card"><span>活动任务</span><strong>{{ status.activeRuns }}</strong><p>包含排队、运行和停止中的任务</p></article>
          <article class="metric-card"><span>系统时区</span><strong class="metric-card__name">{{ status.configuredTimezone }}</strong><p>服务器时间 {{ formatTime(status.serverTime) }}</p></article>
        </div>
        <article class="content-card service-status-card">
          <header><h2>服务实时状态</h2><p>页面可见时每 5 秒更新。Runner 或 Scheduler 心跳过期会明确显示离线。</p></header>
          <div class="service-status-list">
            <div v-for="item in status.services" :key="item.name" class="service-status-row">
              <span class="status-dot" :class="item.status === 'ACTIVE' ? 'status-dot--online' : 'status-dot--offline'"></span>
              <div><strong>{{ item.name }}</strong><small>{{ item.status === 'ACTIVE' ? '运行中' : '离线或心跳过期' }}</small></div>
              <span>最近心跳：{{ formatTime(item.heartbeatAt) }}</span>
            </div>
          </div>
        </article>
      </template>
    </div>

    <div v-else-if="activeTab === 'settings'">
      <div v-if="loading" class="content-card loading-state">正在读取设置…</div>
      <div v-else class="settings-stack">
        <SettingsSection section-id="identity" title="系统与登录状态" description="名称、时区、登录会话和敏感操作验证" :open="openSections.has('identity')" @toggle="toggleSection('identity')"><div class="form-grid">
          <label class="field"><span>系统名称</span><input v-model="values['system.name']" maxlength="80" required /></label>
          <div class="field"><span>系统时区</span><SearchCombobox v-model="values['system.timezone']" :options="timezoneOptions" appearance="form" search-placeholder="搜索 IANA 时区…" /><small>浏览器：{{ browserTimezone }}；服务器检测：{{ serverTimezone || '未可靠检测' }}。不会未经确认覆盖现有设置。</small></div>
          <label class="field"><span>闲置有效期（秒）</span><input v-model.number="values['security.session_idle_seconds']" type="number" min="900" max="604800" /></label>
          <label class="field"><span>绝对有效期（秒）</span><input v-model.number="values['security.session_absolute_seconds']" type="number" min="3600" max="604800" /><small>不能短于闲置有效期。</small></label>
          <label class="field"><span>敏感操作复验窗口（秒）</span><input v-model.number="values['security.reauth_seconds']" type="number" min="60" max="3600" /></label>
          <label class="field"><span>每用户最多会话数</span><input v-model.number="values['security.max_sessions_per_user']" type="number" min="1" max="20" /></label>
        </div></SettingsSection>
        <SettingsSection section-id="network" title="管理区网络保护" description="真实客户端地址、可信网络和反向代理" :open="openSections.has('network')" @toggle="toggleSection('network')"><div class="form-grid">
          <label class="field"><span>访问模式</span><select v-model="values['security.management_network_mode']"><option value="ACCOUNT_ONLY">仅账户与权限</option><option value="TRUSTED_NETWORKS">账户 + 可信网络</option></select></label>
          <div class="network-observation"><span>系统识别的当前地址</span><strong>{{ values['request.client_ip'] }}</strong><button class="text-button" type="button" @click="addCurrentAddress">加入当前地址 /32 或 /128</button></div>
          <label class="field field--wide"><span>管理区可信 CIDR</span><textarea v-model="managementCidrs" rows="5" placeholder="每行一个，例如 203.0.113.18/32"></textarea><small>后端会阻止把当前地址排除在外的自锁配置。</small></label>
          <label class="field field--wide"><span>可信反向代理 CIDR</span><textarea v-model="proxyCidrs" rows="4" placeholder="只填写确实代收请求的代理地址"></textarea><small>先单独保存代理，再确认上方识别地址。</small></label>
        </div></SettingsSection>
        <SettingsSection section-id="packages" title="功能包与数据源边界" description="归档格式、解压安全和文件容量限制" :open="openSections.has('packages')" @toggle="toggleSection('packages')"><div class="form-grid">
          <fieldset class="field field--wide package-formats"><legend>允许上传的功能包格式</legend><label v-for="format in formatOptions" :key="format.id"><input type="checkbox" :checked="stringList(values['feature.allowed_package_formats']).includes(format.id)" @change="toggleFormat(format.id, ($event.target as HTMLInputElement).checked)" /><span><strong>{{ format.label }}</strong><small>{{ format.extensions }}</small></span></label></fieldset>
          <label class="field"><span>功能包上限（字节）</span><input v-model.number="values['feature.package_max_bytes']" type="number" min="1048576" /></label>
          <label class="field"><span>最大条目数</span><input v-model.number="values['feature.package_max_entries']" type="number" min="10" /></label>
          <label class="field"><span>解压单文件上限（字节）</span><input v-model.number="values['feature.package_max_entry_bytes']" type="number" min="1048576" /></label>
          <label class="field"><span>解压总量上限（字节）</span><input v-model.number="values['feature.package_max_total_bytes']" type="number" min="1048576" /></label>
          <label class="field"><span>最大压缩比</span><input v-model.number="values['feature.package_max_compression_ratio']" type="number" min="2" /></label>
          <label class="field"><span>数据源上限（字节）</span><input v-model.number="values['feature.data_source_max_bytes']" type="number" min="1024" /></label>
        </div></SettingsSection>
        <SettingsSection section-id="dependencies" title="Python 依赖准备" description="隔离环境、依赖源和离线 wheel 策略" :open="openSections.has('dependencies')" @toggle="toggleSection('dependencies')"><div class="form-grid">
          <label class="field field--wide"><span>依赖源</span><input v-model="values['dependencies.index_url']" type="url" required /><small>只接受不携带账号密码的 HTTPS 地址。</small></label>
          <label class="field"><span>单条命令超时（秒）</span><input v-model.number="values['dependencies.download_timeout_seconds']" type="number" min="30" max="3600" /></label>
          <label class="field"><span>缓存上限（字节）</span><input v-model.number="values['dependencies.cache_max_bytes']" type="number" min="104857600" /></label>
          <label class="field field--wide toggle-field"><span><strong>仅使用功能包内 wheels</strong><small>离线环境启用；缺少间接依赖时准备会失败。</small></span><input v-model="values['dependencies.offline_mode']" class="switch" type="checkbox" /></label>
        </div></SettingsSection>
        <SettingsSection section-id="runner" title="Runner 与任务日志" description="并发、停止、心跳、结构化报表和任务日志保留" :open="openSections.has('runner')" @toggle="toggleSection('runner')"><div class="form-grid">
          <label class="field"><span>最大并发任务</span><input v-model.number="values['runner.max_concurrency']" type="number" min="1" max="16" /></label><label class="field"><span>最大排队数</span><input v-model.number="values['runner.max_queued_runs']" type="number" min="1" max="10000" /></label>
          <label class="field"><span>轮询间隔（毫秒）</span><input v-model.number="values['runner.poll_interval_ms']" type="number" min="100" max="5000" /></label><label class="field"><span>停止宽限期（秒）</span><input v-model.number="values['runner.stop_grace_seconds']" type="number" min="1" max="300" /></label>
          <label class="field"><span>心跳间隔（秒）</span><input v-model.number="values['runner.heartbeat_seconds']" type="number" min="1" max="60" /></label><label class="field"><span>失联判定（秒）</span><input v-model.number="values['runner.stale_after_seconds']" type="number" min="3" max="600" /><small>至少为心跳间隔的 3 倍。</small></label>
          <label class="field"><span>日志批量条数</span><input v-model.number="values['runner.log_batch_size']" type="number" min="1" max="500" /></label><label class="field"><span>日志刷新间隔（毫秒）</span><input v-model.number="values['runner.log_flush_ms']" type="number" min="50" max="5000" /></label>
          <label class="field"><span>单条日志上限（字节）</span><input v-model.number="values['runner.max_event_bytes']" type="number" min="1024" max="262144" /></label><label class="field"><span>日志上下文上限（字节）</span><input v-model.number="values['runner.max_context_bytes']" type="number" min="1024" max="524288" /></label>
          <label class="field"><span>单次报表明细上限</span><input v-model.number="values['runner.report_max_items']" type="number" min="1" max="1000000" /><small>默认 60000；修改只影响之后启动的任务。</small></label>
          <label class="field"><span>任务日志保留天数</span><input v-model.number="values['logs.retention_days']" type="number" min="0" max="3650" /><small>默认 180；0 表示不自动清理。</small></label><label class="field"><span>默认最长运行（秒）</span><input v-model.number="values['runner.default_max_runtime_seconds']" type="number" min="0" max="2592000" /><small>0 表示不设平台超时。</small></label>
        </div></SettingsSection>
        <SettingsSection section-id="platform-logs" title="平台程序日志与更新包" description="平台日志保留、容量与更新包上限" :open="openSections.has('platform-logs')" @toggle="toggleSection('platform-logs')"><div class="form-grid">
          <label class="field"><span>保留天数</span><input v-model.number="values['system_logs.retention_days']" type="number" min="1" max="3650" /><small>默认 180 天。</small></label>
          <label class="field"><span>可选容量上限（MiB）</span><input v-model.number="systemLogMaxMiB" type="number" min="0" max="1048576" /><small>0 表示不设容量限制；当天文件不会被容量策略删除。</small></label>
          <label class="field"><span>更新包上限（MiB）</span><input v-model.number="updateMaxMiB" type="number" min="10" max="2048" /><small>只限制签名的 .fcup 系统更新包，不影响功能包。</small></label>
        </div></SettingsSection>
        <SettingsSection section-id="scheduler" title="Scheduler" description="轮询、错过容差与调度服务心跳" :open="openSections.has('scheduler')" @toggle="toggleSection('scheduler')"><div class="form-grid">
          <label class="field"><span>轮询间隔（秒）</span><input v-model.number="values['scheduler.poll_interval_seconds']" type="number" min="1" max="60" /></label><label class="field"><span>错过容差（秒）</span><input v-model.number="values['scheduler.misfire_grace_seconds']" type="number" min="0" max="3600" /></label>
          <label class="field"><span>心跳间隔（秒）</span><input v-model.number="values['scheduler.heartbeat_seconds']" type="number" min="1" max="60" /></label><label class="field"><span>失联判定（秒）</span><input v-model.number="values['scheduler.stale_after_seconds']" type="number" min="3" max="600" /></label>
        </div></SettingsSection>
      </div>
    </div>

    <div v-else-if="activeTab === 'logs'" class="settings-stack">
      <article class="content-card program-log-card">
        <header><div><h2>平台程序运行日志</h2><p>只展示平台服务日志，不包含业务脚本输出。页面可见时每 3 秒读取增量。</p></div><button class="secondary-button" type="button" @click="downloadSystemLog">下载当前服务日志</button></header>
        <div class="program-log-filters"><label class="field"><span>服务</span><select v-model="logService"><option value="all">全部服务</option><option value="web">Web</option><option value="runner">Runner</option><option value="scheduler">Scheduler</option><option value="launcher">Launcher</option></select></label><label class="field"><span>日期（UTC）</span><input v-model="logDate" type="date" /></label><label class="field"><span>级别</span><select v-model="logLevel"><option value="">全部级别</option><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option><option value="CRITICAL">CRITICAL</option></select></label></div>
        <div class="program-log-console" aria-live="polite"><div v-if="logEntries.length === 0" class="program-log-empty">{{ logLoading ? '正在读取日志…' : '当前筛选条件下没有日志' }}</div><article v-for="(item, index) in logEntries" :key="`${item.timestamp}-${item.service}-${index}`" class="program-log-line" :class="`program-log-line--${item.level.toLowerCase()}`"><time>{{ new Date(item.timestamp).toLocaleString() }}</time><span>{{ item.service }}</span><b>{{ item.level }}</b><code>{{ item.message }}</code><pre v-if="item.exception">{{ item.exception }}</pre></article></div>
      </article>
    </div>

    <div v-else-if="activeTab === 'updates'" class="settings-stack">
      <article class="content-card update-overview-card">
        <header>
          <div>
            <h2>签名更新包</h2>
            <p>只接受由交付方离线签名的 .fcup 文件。平台先验证，再由容器内稳定启动器执行、健康检查并切换版本。</p>
          </div>
          <label class="primary-button update-upload-button" :class="{ disabled: updateUploadBusy || busy }">
            {{ updateUploadBusy ? '正在校验…' : '上传更新包' }}
            <input ref="updateFileInput" type="file" accept=".fcup" :disabled="updateUploadBusy || busy" @change="uploadUpdatePackage" />
          </label>
        </header>
        <div v-if="updateConnectionError" class="update-connection-note" role="status">{{ updateConnectionError }}</div>
        <div v-if="!updateOverview" class="loading-state">{{ updateLoading ? '正在读取更新状态…' : '尚未取得更新状态' }}</div>
        <template v-else>
          <div class="update-facts">
            <div><span>当前版本</span><strong>{{ updateOverview.currentVersion }}</strong></div>
            <div><span>运行平台</span><strong>{{ updateOverview.runtimePlatform }}</strong></div>
            <div><span>更新启动器</span><strong :class="updateOverview.supervisor.available ? 'status-text--success' : 'status-text--danger'">{{ updateOverview.supervisor.available ? '在线' : '不可用' }}</strong></div>
            <div><span>活动任务</span><strong>{{ updateOverview.activeRuns }}</strong></div>
          </div>
          <p v-if="!updateOverview.supervisor.available" class="inline-notice inline-notice--warning">本地开发模式可以验证更新包，但不能执行更新。Linux Docker 交付环境由稳定启动器接管更新。</p>
          <p v-else-if="updateOverview.activeRuns > 0" class="inline-notice inline-notice--warning">仍有 {{ updateOverview.activeRuns }} 个任务处于排队、运行或停止中。全部结束后才能更新或回退。</p>
          <div class="update-rollback-row">
            <div><strong>保留数据回退</strong><span>只回退程序到最近的兼容版本，不把 SQLite 恢复成历史数据。</span></div>
            <button class="secondary-button" type="button" :disabled="busy || !updateOverview.canRollback" @click="openReauth('rollback')">回退到 {{ updateOverview.rollbackTargetVersion ?? '上一版本' }}</button>
          </div>
        </template>
      </article>

      <article class="content-card update-history-card">
        <header><div><h2>更新任务</h2><p>状态写入数据库；即使页面关闭或服务重启，也可以继续查看进度和结果。</p></div><button class="text-button" type="button" :disabled="updateLoading" @click="loadUpdates">刷新</button></header>
        <div v-if="updateOverview?.items.length" class="update-records">
          <article v-for="item in updateOverview.items" :key="item.id" class="update-record">
            <div class="update-record__top">
              <div>
                <span class="status-pill" :class="`status-pill--${item.status.toLowerCase().replace('_', '-')}`">{{ updateStatusLabel(item.status) }}</span>
                <strong>{{ item.operation === 'APPLY' ? `${item.sourceVersion} → ${item.targetVersion}` : `回退 ${item.sourceVersion} → ${item.targetVersion}` }}</strong>
              </div>
              <time>{{ new Date(item.createdAt * 1000).toLocaleString() }}</time>
            </div>
            <div class="update-progress" :aria-label="`更新进度 ${item.progress}%`"><span :style="{ width: `${item.progress}%` }"></span></div>
            <div class="update-record__meta"><span>{{ updateStageLabel(item.stage) }}</span><span>{{ item.progress }}%</span><span>{{ formatBytes(item.packageSize) }}</span><span>{{ item.actorDisplayName ?? '系统' }} · {{ item.clientIp ?? '本机' }}</span></div>
            <ul v-if="item.releaseNotes.length" class="update-notes"><li v-for="note in item.releaseNotes" :key="note">{{ note }}</li></ul>
            <p v-if="item.errorMessage" class="form-error update-record__error">{{ item.errorMessage }}</p>
            <div v-if="item.canApply" class="update-record__actions">
              <span>签名和文件摘要已通过验证</span>
              <button class="primary-button" type="button" :disabled="busy || !updateOverview.supervisor.available || updateOverview.activeRuns > 0 || updateOverview.updateInProgress" @click="openReauth('apply', item.id)">安装此更新</button>
            </div>
            <div v-else-if="item.canRetry" class="update-record__actions"><span>原签名包仍可用于新的独立尝试</span><button class="secondary-button" type="button" :disabled="busy || updateOverview.updateInProgress" @click="openReauth('retry', item.id)">重新尝试</button></div>
          </article>
        </div>
        <div v-else class="loading-state">尚未上传更新包</div>
      </article>
      <PaginationBar v-if="updatePagination.total > 0" :pagination="updatePagination" :disabled="updateLoading" @change="changeUpdatePage" />
    </div>

    <div v-else class="release-list">
      <article v-for="release in releaseItems" :key="release.version" class="content-card release-card"><header><div><strong>{{ release.version }}</strong><h2>{{ release.title }}</h2></div><time>{{ release.date }}</time></header><ul><li v-for="item in release.items" :key="item">{{ item }}</li></ul></article>
      <div v-if="releaseItems.length === 0" class="content-card loading-state">暂无更新记录</div>
      <PaginationBar v-if="releasePagination.total > 0" :pagination="releasePagination" @change="changeReleasePage" />
    </div>
    </div></Transition>

    <ModalDialog :open="reauthOpen" title="再次验证身份" :description="reauthDescription()" width="small" :closeable="!busy" @close="reauthOpen = false"><form id="settings-reauth" class="form-stack" @submit.prevent="confirmReauth"><label class="field"><span>当前密码</span><input v-model="password" type="password" autocomplete="current-password" required /></label><p v-if="reauthError" class="form-error">{{ reauthError }}</p></form><template #footer><button class="secondary-button" type="button" @click="reauthOpen = false">取消</button><button class="primary-button" type="submit" form="settings-reauth" :disabled="busy">{{ reauthAction === 'apply' ? '验证并安装' : reauthAction === 'retry' ? '验证并重新尝试' : reauthAction === 'rollback' ? '验证并回退' : '验证并保存' }}</button></template></ModalDialog>
  </section>
</template>
