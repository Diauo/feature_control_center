<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import FeatureConfigDrawer from '@/components/FeatureConfigDrawer.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest, downloadFile } from '@/lib/api'
import { featurePackageExtensions, uploadFeaturePackage } from '@/lib/featurePackages'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { Customer, CustomerFeature, FeatureDefinition, FeatureVersion, Paginated, Pagination } from '@/types'

interface CopyResult {
  customerId: string
  status: 'COPIED' | 'SKIPPED_EXISTS' | 'FAILED'
  customerFeatureId: string | null
  message: string
  errorCode?: string
}

const session = useSessionStore()
const router = useRouter()
const route = useRoute()
const definitions = ref<FeatureDefinition[]>([])
const customerFeatures = ref<CustomerFeature[]>([])
const customers = ref<Customer[]>([])
const packageFile = ref<File | null>(null)
const loading = ref(true)
const busy = ref(false)
const runningId = ref<string | null>(null)
const error = ref('')
const reauthOpen = ref(false)
const reauthPassword = ref('')
const reauthError = ref('')
const copyOpen = ref(false)
const copySource = ref<CustomerFeature | null>(null)
const copyTargetIds = ref<string[]>([])
const copyResults = ref<CopyResult[]>([])
const configFeature = ref<{ id: string; name: string } | null>(null)
const allowedFormats = ref<string[]>(['zip'])
const uploadExtensions = computed(() => featurePackageExtensions(allowedFormats.value))
const uploadAccept = computed(() => uploadExtensions.value.join(','))
const uploadFormatLabel = computed(() => uploadExtensions.value.join('、'))
let pending: (() => Promise<void>) | null = null
let refreshTimer: number | null = null
let loadSequence = 0
let customerFeatureSequence = 0
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })

onMounted(async () => {
  await load()
  refreshTimer = window.setInterval(() => {
    if (definitions.value.some((definition) => definition.versions.some((version) => version.status === 'PREPARING'))) {
      void refreshPreparing()
    }
  }, 2000)
})
onBeforeUnmount(() => { if (refreshTimer !== null) window.clearInterval(refreshTimer) })
watch([() => session.currentCustomerId, () => session.customerScopeMode], () => {
  copyOpen.value = false
  void loadCustomerFeatures().catch((reason) => {
    error.value = message(reason, '当前客户功能加载失败')
  })
})

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  try {
    const [definitionResult, customerResult, settingResult] = await Promise.all([
      apiRequest<Paginated<FeatureDefinition>>(`/api/admin/feature-definitions?page=${pagination.value.page}&pageSize=${pagination.value.pageSize}`),
      apiRequest<{ items: Customer[] }>('/api/customers'),
      apiRequest<{ values: Record<string, unknown> }>('/api/admin/settings'),
    ])
    if (sequence !== loadSequence) return
    definitions.value = definitionResult.items
    pagination.value = definitionResult.pagination
    customers.value = customerResult.items
    allowedFormats.value = Array.isArray(settingResult.values['feature.allowed_package_formats'])
      ? settingResult.values['feature.allowed_package_formats'].map(String)
      : ['zip']
    await loadCustomerFeatures()
  } catch (reason) { if (sequence === loadSequence) error.value = message(reason, '功能版本加载失败') }
  finally { if (sequence === loadSequence) loading.value = false }
}

async function loadCustomerFeatures(): Promise<void> {
  const customerId = session.currentCustomerId
  const allCustomers = session.isAllCustomers
  const sequence = ++customerFeatureSequence
  customerFeatures.value = []
  if (!customerId || allCustomers) { customerFeatures.value = []; return }
  const result = await apiRequest<{ items: CustomerFeature[] }>(`/api/customers/${encodeURIComponent(customerId)}/features`)
  if (sequence === customerFeatureSequence && !session.isAllCustomers && session.currentCustomerId === customerId) {
    customerFeatures.value = result.items
    const requested = typeof route.query.config === 'string' ? route.query.config : ''
    if (requested) {
      const match = result.items.find((item) => item.id === requested)
      if (match) configFeature.value = { id: match.id, name: `${match.customerName} · ${match.name}` }
    }
  }
}

async function refreshPreparing(): Promise<void> {
  try {
    const page = pagination.value.page
    const pageSize = pagination.value.pageSize
    const result = await apiRequest<Paginated<FeatureDefinition>>(`/api/admin/feature-definitions?page=${pagination.value.page}&pageSize=${pagination.value.pageSize}`)
    if (pagination.value.page !== page || pagination.value.pageSize !== pageSize) return
    definitions.value = result.items
    pagination.value = result.pagination
    await loadCustomerFeatures()
  } catch (reason) { error.value = message(reason, '依赖状态刷新失败') }
}

function onPackage(event: Event): void {
  packageFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function upload(): Promise<void> {
  if (!packageFile.value || !session.currentCustomerId || session.isAllCustomers) return
  await sensitive(async () => {
    busy.value = true
    try {
      await uploadFeaturePackage(session.currentCustomerId!, packageFile.value!)
      const uploadedName = packageFile.value!.name
      packageFile.value = null
      await load()
      notify.success('功能包已登记', { description: `${uploadedName} 正在准备隔离依赖环境` })
    } finally { busy.value = false }
  })
}

async function retry(version: FeatureVersion): Promise<void> {
  await sensitive(async () => {
    busy.value = true
    try {
      await apiRequest(`/api/admin/feature-versions/${version.id}/prepare`, { method: 'POST' })
      await load()
      notify.success('依赖准备已重新提交', { description: `代码版本 ${version.versionNumber}` })
    }
    finally { busy.value = false }
  })
}

async function startRun(definitionId: string): Promise<void> {
  const feature = currentCustomerFeature(definitionId)
  if (!feature || feature.status !== 'ACTIVE' || !feature.configurationComplete) return
  runningId.value = feature.id
  error.value = ''
  try {
    const result = await apiRequest<{ run: { requestId: string } }>(`/api/customer-features/${feature.id}/runs`, { method: 'POST' })
    notify.success('任务已提交', { description: `${feature.customerName} · 正在打开实时日志` })
    await router.push(`/runs/${result.run.requestId}`)
  } catch (reason) {
    error.value = message(reason, '任务创建失败')
    notify.error('任务提交失败', { description: error.value })
  } finally {
    runningId.value = null
  }
}

async function downloadDefaultDataSource(version: FeatureVersion): Promise<void> {
  error.value = ''
  try {
    await downloadFile(`/api/admin/feature-versions/${version.id}/default-data-source/download`)
    notify.success('默认数据源已开始下载', { description: version.defaultDataSource?.filename ?? `代码版本 ${version.versionNumber}` })
  } catch (reason) {
    error.value = message(reason, '默认数据源下载失败')
    notify.error('默认数据源下载失败', { description: error.value })
  }
}

async function activate(definition: FeatureDefinition, version: FeatureVersion): Promise<void> {
  const feature = customerFeatures.value.find((item) => item.definitionId === definition.id)
  if (!feature) { error.value = '当前客户尚未登记这个功能，请先从已有客户复制功能。'; return }
  await sensitive(async () => {
    busy.value = true
    try {
      await apiRequest(`/api/admin/customer-features/${feature.id}/activate-version`, {
        method: 'POST', body: JSON.stringify({ versionId: version.id, useDefaultDataSource: false }),
      })
      await loadCustomerFeatures()
      notify.success('功能版本已切换', { description: `${definition.name} · 代码版本 ${version.versionNumber}` })
    } finally { busy.value = false }
  })
}

function openConfig(definition: FeatureDefinition): void {
  const feature = currentCustomerFeature(definition.id)
  if (!feature) return
  configFeature.value = { id: feature.id, name: `${feature.customerName} · ${definition.name}` }
}

function closeConfig(): void {
  configFeature.value = null
}

function openCopy(definitionId: string): void {
  const source = customerFeatures.value.find((item) => item.definitionId === definitionId)
  if (!source) return
  copySource.value = source
  copyTargetIds.value = []
  copyResults.value = []
  copyOpen.value = true
}

async function copyFeature(): Promise<void> {
  if (!copySource.value || copyTargetIds.value.length === 0) return
  await sensitive(async () => {
    busy.value = true
    try {
      const result = await apiRequest<{ items: CopyResult[] }>(
        `/api/admin/customer-features/${copySource.value!.id}/copy`,
        { method: 'POST', body: JSON.stringify({ targetCustomerIds: copyTargetIds.value }) },
      )
      copyResults.value = result.items
      const copiedCount = result.items.filter((item) => item.status === 'COPIED').length
      notify.success('快捷复制已完成', { description: `成功复制给 ${copiedCount} 个客户` })
    } finally { busy.value = false }
  })
}

async function sensitive(action: () => Promise<void>): Promise<void> {
  error.value = ''
  try { await action() }
  catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') {
      pending = action; reauthPassword.value = ''; reauthError.value = ''; reauthOpen.value = true; return
    }
    error.value = message(reason, '操作失败')
    notify.error('功能操作失败', { description: error.value })
  }
}

async function confirmReauth(): Promise<void> {
  if (!pending) return
  busy.value = true
  try {
    await session.reauthenticate(reauthPassword.value)
    const action = pending; pending = null; reauthOpen.value = false; busy.value = false
    await sensitive(action)
  } catch (reason) { reauthError.value = message(reason, '密码验证失败') }
  finally { busy.value = false }
}

function currentVersion(definitionId: string): string | null {
  return currentCustomerFeature(definitionId)?.versionId ?? null
}
function currentCustomerFeature(definitionId: string): CustomerFeature | null { return customerFeatures.value.find((item) => item.definitionId === definitionId) ?? null }
function runDisabledReason(feature: CustomerFeature | null): string | undefined {
  if (!feature) return '当前客户尚未登记这个功能'
  if (feature.status !== 'ACTIVE') return '功能依赖或数据源尚未准备完成'
  if (!feature.configurationComplete) return '请先完成必填配置（本页「配置管理」）'
  return undefined
}
function customerName(customerId: string): string { return customers.value.find((item) => item.id === customerId)?.name ?? customerId }
function message(reason: unknown, fallback: string): string { return reason instanceof ApiError ? reason.message : fallback }
function formatDate(value: number): string { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(value * 1000) }
function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }
</script>

<template>
  <section>
    <div class="page-heading"><div><h1>功能管理</h1><p>只静态解析归档元数据，不导入或执行上传代码；相同依赖环境会跨版本复用。</p></div></div>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <p v-if="session.isAllCustomers" class="inline-notice inline-notice--warning">当前正在查看全部客户。登记新版本、切换客户版本或复制功能前，请先在顶部选择一个具体客户。</p>
    <article class="content-card upload-panel">
      <div><h2>登记新版本</h2><p>归档根目录必须包含 <code>__init__.py</code>；当前允许 {{ uploadFormatLabel }}，可携带 requirements.txt、wheels/ 和默认数据源。</p></div>
      <div class="upload-panel__actions"><label class="secondary-button upload-button">{{ packageFile?.name ?? '选择功能包' }}<input type="file" :accept="uploadAccept" @change="onPackage" /></label><button class="primary-button" type="button" :disabled="busy || !packageFile || !session.currentCustomerId || session.isAllCustomers" :title="session.isAllCustomers ? '上传前请先选择一个具体客户' : undefined" @click="upload">{{ busy ? '正在处理…' : '上传并校验' }}</button></div>
    </article>
    <div v-if="loading" class="content-card loading-state">正在读取版本…</div>
    <article v-else-if="definitions.length === 0" class="content-card empty-state-card"><div class="empty-icon">＋</div><h2>尚未登记功能</h2><p>首次上传某个功能时，会为当前客户创建独立的配置和默认数据源副本。</p></article>
    <div v-else class="definition-list">
      <article v-for="definition in definitions" :key="definition.id" class="content-card definition-card">
        <header><div><h2>{{ definition.name }}</h2></div><div class="row-actions"><span>{{ definition.versions.length }} 个版本</span><button v-if="currentCustomerFeature(definition.id)" class="primary-button secondary-button--compact" type="button" :disabled="busy || runningId !== null || Boolean(runDisabledReason(currentCustomerFeature(definition.id)))" :title="runDisabledReason(currentCustomerFeature(definition.id))" @click="startRun(definition.id)">{{ runningId === currentCustomerFeature(definition.id)?.id ? '正在创建…' : '运行功能' }}</button><button v-if="currentCustomerFeature(definition.id)" class="secondary-button secondary-button--compact" type="button" :disabled="busy || runningId !== null" @click="openConfig(definition)">配置管理</button><button v-if="currentVersion(definition.id)" class="secondary-button secondary-button--compact" type="button" :disabled="runningId !== null" @click="openCopy(definition.id)">复制给其他客户</button></div></header>
        <div class="table-scroll"><table><thead><tr><th>版本</th><th>状态</th><th>包与时间</th><th>数据源</th><th class="align-right">操作</th></tr></thead><tbody>
          <tr v-for="version in definition.versions" :key="version.id"><td><strong>代码版本 {{ version.versionNumber }}</strong><span v-if="currentVersion(definition.id) === version.id" class="block-copy">当前客户正在使用</span></td><td><span class="status-pill" :class="version.status === 'READY' ? 'status-pill--on' : version.status === 'DEPENDENCY_FAILED' ? 'status-pill--danger' : 'status-pill--warn'">{{ version.status }}</span><small v-if="version.prepareError" class="error-copy">{{ version.prepareError }}</small></td><td class="muted-cell">{{ version.packageFilename }}<span class="block-copy">{{ formatDate(version.createdAt) }}</span></td><td class="muted-cell">{{ version.defaultDataSource?.filename ?? '无默认文件' }}</td><td><div class="row-actions"><button v-if="version.defaultDataSource" class="text-button" type="button" @click="downloadDefaultDataSource(version)">下载默认文件</button><button v-if="version.status === 'DEPENDENCY_FAILED'" class="text-button" type="button" :disabled="busy" @click="retry(version)">重试依赖</button><button v-if="version.status === 'READY' && currentVersion(definition.id) && currentVersion(definition.id) !== version.id" class="text-button" type="button" :disabled="busy" @click="activate(definition, version)">用于当前客户</button></div></td></tr>
        </tbody></table></div>
      </article>
    </div>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />
    <ModalDialog :open="copyOpen" title="复制功能给其他客户" description="代码版本会共享；配置值、密钥、定时任务、运行日志和来源客户当前数据源不会复制。" width="large" :closeable="!busy" @close="copyOpen = false">
      <div v-if="copySource" class="form-stack">
        <div class="copy-summary"><span>来源功能</span><strong>{{ copySource.name }} · 代码版本 {{ copySource.versionNumber }}</strong><p>每个目标客户会从这个代码版本的包内默认文件，新建自己独立的数据源第 1 版。</p></div>
        <div v-if="copyResults.length" class="copy-results">
          <div v-for="result in copyResults" :key="result.customerId" class="copy-result-row"><div><strong>{{ customerName(result.customerId) }}</strong><small>{{ result.message }}</small></div><span class="status-pill" :class="result.status === 'COPIED' ? 'status-pill--on' : result.status === 'FAILED' ? 'status-pill--danger' : 'status-pill--warn'">{{ result.status === 'COPIED' ? '已复制' : result.status === 'FAILED' ? '失败' : '已存在' }}</span></div>
        </div>
        <div v-else class="check-grid">
          <label v-for="customer in customers.filter((item) => item.isActive && item.id !== session.currentCustomerId)" :key="customer.id" class="check-card"><input v-model="copyTargetIds" type="checkbox" :value="customer.id" /><span><strong>{{ customer.name }}</strong><small>{{ customer.description || '无客户说明' }}</small></span></label>
          <p v-if="customers.filter((item) => item.isActive && item.id !== session.currentCustomerId).length === 0" class="muted-cell">没有其他已启用客户。</p>
        </div>
      </div>
      <template #footer><button class="secondary-button" type="button" :disabled="busy" @click="copyOpen = false">{{ copyResults.length ? '完成' : '取消' }}</button><button v-if="!copyResults.length" class="primary-button" type="button" :disabled="busy || copyTargetIds.length === 0" @click="copyFeature">{{ busy ? '正在复制…' : `复制到 ${copyTargetIds.length} 个客户` }}</button></template>
    </ModalDialog>
    <ModalDialog :open="reauthOpen" title="验证管理员身份" description="上传代码、准备依赖或切换版本属于敏感操作。" :closeable="!busy" width="small" @close="reauthOpen = false"><form id="feature-reauth" class="form-stack" @submit.prevent="confirmReauth"><label class="field"><span>当前密码</span><input v-model="reauthPassword" type="password" autocomplete="current-password" required /></label><p v-if="reauthError" class="form-error">{{ reauthError }}</p></form><template #footer><button class="secondary-button" type="button" @click="reauthOpen = false">取消</button><button class="primary-button" type="submit" form="feature-reauth" :disabled="busy">继续</button></template></ModalDialog>
    <FeatureConfigDrawer v-if="configFeature" :feature-id="configFeature.id" :feature-name="configFeature.name" @close="closeConfig" @saved="loadCustomerFeatures" />
  </section>
</template>
