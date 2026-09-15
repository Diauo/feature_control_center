<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import FeatureConfigDrawer from '@/components/FeatureConfigDrawer.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import SearchCombobox from '@/components/SearchCombobox.vue'
import { ApiError, apiRequest, downloadFile } from '@/lib/api'
import { featurePackageExtensions, uploadFeaturePackage } from '@/lib/featurePackages'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature, Paginated, Pagination } from '@/types'

const session = useSessionStore()
const router = useRouter()
const route = useRoute()
const features = ref<CustomerFeature[]>([])
const loading = ref(false)
const busyId = ref<string | null>(null)
const error = ref('')
const configFeature = ref<CustomerFeature | null>(null)
const search = ref('')
const statusFilter = ref('')
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const displayedScope = ref('')
const uploadOpen = ref(false)
const uploadBusy = ref(false)
const uploadFormatsLoading = ref(false)
const uploadFormatsReady = ref(false)
const uploadFile = ref<File | null>(null)
const uploadCustomerId = ref('')
const uploadError = ref('')
const uploadReauthOpen = ref(false)
const uploadReauthBusy = ref(false)
const uploadReauthPassword = ref('')
const uploadReauthError = ref('')
const allowedFormats = ref<string[]>(['zip'])
let requestSequence = 0

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 11) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
const readyCount = computed(() => features.value.filter((item) => item.status === 'ACTIVE' && item.configurationComplete).length)
const scopeReady = computed(() => displayedScope.value === (session.isAllCustomers ? 'all' : session.currentCustomerId ?? ''))
const uploadExtensions = computed(() => featurePackageExtensions(allowedFormats.value))
const uploadAccept = computed(() => uploadExtensions.value.join(','))
const uploadFormatLabel = computed(() => uploadExtensions.value.join('、') || '暂未启用任何格式')
const uploadCustomerOptions = computed(() => session.customers
  .filter((customer) => customer.isActive)
  .map((customer) => ({ value: customer.id, label: customer.name, description: customer.description || '已启用客户' })))
const uploadCustomerName = computed(() => session.customers.find((customer) => customer.id === uploadCustomerId.value)?.name ?? '未选择')
const statusCopy: Record<CustomerFeature['status'], string> = {
  ACTIVE: '可运行', PREPARING: '准备依赖中', WAITING_DATA_SOURCE: '等待数据源',
  DEPENDENCY_FAILED: '依赖准备失败', DISABLED: '已停用',
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
    const requestedConfig = typeof route.query.config === 'string' ? route.query.config : ''
    configFeature.value = session.isAdmin ? result.items.find((item) => item.id === requestedConfig) ?? null : null
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
    notify.success('任务已提交', { description: `${feature.customerName} · 正在打开实时日志` })
    await router.push(`/runs/${result.run.requestId}`)
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
function openFeatureUpload(): void {
  uploadFile.value = null
  uploadCustomerId.value = session.isAllCustomers ? '' : session.currentCustomerId ?? ''
  uploadError.value = ''
  uploadReauthOpen.value = false
  uploadFormatsReady.value = false
  uploadOpen.value = true
  void loadUploadFormats()
}
function closeFeatureUpload(): void {
  if (uploadBusy.value || uploadReauthBusy.value) return
  uploadOpen.value = false
  uploadReauthOpen.value = false
  uploadFile.value = null
  uploadError.value = ''
}
async function loadUploadFormats(): Promise<void> {
  uploadFormatsLoading.value = true
  try {
    const result = await apiRequest<{ values: Record<string, unknown> }>('/api/admin/settings')
    const configured = result.values['feature.allowed_package_formats']
    allowedFormats.value = Array.isArray(configured) ? configured.map(String) : ['zip']
    uploadFormatsReady.value = featurePackageExtensions(allowedFormats.value).length > 0
  } catch (reason) {
    uploadFormatsReady.value = false
    uploadError.value = reason instanceof ApiError ? reason.message : '无法读取允许的功能包格式'
  } finally {
    uploadFormatsLoading.value = false
  }
}
function selectFeaturePackage(event: Event): void {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}
async function submitFeatureUpload(): Promise<void> {
  if (!uploadFile.value || !uploadCustomerId.value || !uploadFormatsReady.value || uploadFormatsLoading.value) return
  uploadBusy.value = true
  uploadError.value = ''
  try {
    const filename = uploadFile.value.name
    const customerName = uploadCustomerName.value
    await uploadFeaturePackage(uploadCustomerId.value, uploadFile.value)
    uploadOpen.value = false
    uploadFile.value = null
    await load()
    notify.success('功能包已登记', { description: `${customerName} · ${filename} · 正在准备隔离依赖环境` })
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') {
      uploadReauthPassword.value = ''
      uploadReauthError.value = ''
      uploadOpen.value = false
      uploadReauthOpen.value = true
      return
    }
    uploadError.value = reason instanceof ApiError ? reason.message : '功能包上传失败'
    notify.error('功能包上传失败', { description: uploadError.value })
  } finally {
    uploadBusy.value = false
  }
}
async function confirmUploadReauth(): Promise<void> {
  uploadReauthBusy.value = true
  uploadReauthError.value = ''
  try {
    await session.reauthenticate(uploadReauthPassword.value)
    uploadReauthOpen.value = false
    uploadOpen.value = true
    await submitFeatureUpload()
  } catch (reason) {
    uploadReauthError.value = reason instanceof ApiError ? reason.message : '密码验证失败'
  } finally {
    uploadReauthBusy.value = false
  }
}
function cancelUploadReauth(): void {
  if (uploadReauthBusy.value) return
  uploadReauthOpen.value = false
  uploadReauthPassword.value = ''
  uploadReauthError.value = ''
  uploadOpen.value = true
}
function openConfig(feature: CustomerFeature): void { configFeature.value = feature; void router.replace({ path: '/', query: { config: feature.id } }) }
function closeConfig(): void { configFeature.value = null; void router.replace({ path: '/', query: {} }) }

watch([() => session.currentCustomerId, () => session.customerScopeMode], () => {
  if (!session.isAllCustomers) {
    search.value = ''
    statusFilter.value = ''
  }
  pagination.value.page = 1
  void load()
}, { immediate: true })
watch(() => route.query.config, (value) => {
  if (!session.isAdmin || typeof value !== 'string') { configFeature.value = null; return }
  configFeature.value = features.value.find((item) => item.id === value) ?? null
})
</script>

<template>
  <section>
    <div class="page-heading"><div><h1>{{ greeting }}，{{ session.user?.displayName }}</h1><p>当前正在查看 {{ session.isAllCustomers ? '全部授权客户' : session.currentCustomer?.name ?? '尚未选择客户' }} 的功能与独立数据源。</p></div></div>
    <div class="metric-grid">
      <article class="metric-card metric-card--primary metric-card--actionable"><div class="metric-card__topline"><span>已登记功能</span><button v-if="session.isAdmin" class="metric-card__action" type="button" :disabled="loading || !scopeReady" @click="openFeatureUpload">上传功能包</button></div><strong>{{ pagination.total }}</strong><p>代码版本共享，客户配置与数据源独立</p></article>
      <article class="metric-card"><span>满足运行条件</span><strong>{{ readyCount }}</strong><p>当前页可立即运行的功能</p></article>
      <article class="metric-card"><span>{{ session.isAllCustomers ? '客户范围' : '当前客户' }}</span><strong class="metric-card__name">{{ session.isAllCustomers ? `${session.customers.length} 个客户` : session.currentCustomer?.name ?? '—' }}</strong><p>后端会在每次请求重新校验权限</p></article>
    </div>
    <form v-if="session.isAllCustomers" class="content-card dashboard-filter" @submit.prevent="applyFilters"><label class="field"><span>搜索</span><input v-model="search" placeholder="客户名称或功能名称" /></label><label class="field"><span>状态</span><select v-model="statusFilter"><option value="">全部状态</option><option value="ACTIVE">可运行</option><option value="WAITING_DATA_SOURCE">等待数据源</option><option value="DEPENDENCY_FAILED">依赖失败</option><option value="DISABLED">已停用</option></select></label><button class="primary-button" type="submit" :disabled="loading">查询</button></form>
    <p v-if="error" class="form-error page-error">{{ error }}</p>
    <div class="dashboard-results" :class="{ 'dashboard-results--loading': loading || !scopeReady }">
      <div v-if="loading" class="dashboard-loading" role="status">正在切换客户范围…</div>
      <div v-else-if="!scopeReady" class="dashboard-loading" role="status">切换失败，旧数据仅供查看</div>
      <Transition name="scope" mode="out-in">
        <article v-if="!loading && features.length === 0" :key="`empty-${displayedScope}`" class="content-card empty-state-card"><div class="empty-icon">⌘</div><h2>当前范围还没有功能</h2><p>{{ session.isAdmin ? '可以从上方“已登记功能”卡片上传第一个功能包，或到功能管理复制已有功能。' : '请联系管理员登记功能。' }}</p></article>
        <div v-else :key="`${displayedScope}-${pagination.page}`" class="feature-grid">
          <article v-for="feature in features" :key="feature.id" class="content-card feature-card">
            <div class="feature-card__header"><div><span v-if="session.isAllCustomers" class="customer-badge">客户：{{ feature.customerName }}</span><h2>{{ feature.name }}</h2></div><span class="status-pill" :class="feature.status === 'ACTIVE' ? 'status-pill--on' : feature.status === 'DEPENDENCY_FAILED' ? 'status-pill--danger' : 'status-pill--warn'">{{ statusCopy[feature.status] }}</span></div>
            <p class="feature-card__description">{{ feature.description || '未提供功能说明' }}</p>
            <dl class="feature-facts"><div><dt>配置</dt><dd>{{ feature.configurationComplete ? '已完整设置' : '仍有必填项未设置' }}</dd></div><div><dt>数据源</dt><dd v-if="feature.dataSource">{{ feature.dataSource.filename }} · 第 {{ feature.dataSource.revisionNumber }} 版 · {{ formatBytes(feature.dataSource.size) }}</dd><dd v-else>{{ feature.dataSourceSchema ? '尚未上传' : '此功能不使用数据源' }}</dd></div></dl>
            <div class="feature-actions">
              <button class="primary-button" type="button" :disabled="!scopeReady || loading || busyId === feature.id || feature.status !== 'ACTIVE' || !feature.configurationComplete" @click="startRun(feature)">{{ busyId === feature.id ? '正在创建…' : '运行' }}</button>
              <button v-if="feature.dataSource" class="secondary-button" type="button" :disabled="!scopeReady || loading" @click="downloadDataSource(feature)">下载数据源</button>
              <label v-if="feature.dataSourceSchema" class="secondary-button upload-button" :class="{ 'upload-button--disabled': !scopeReady || loading || busyId === feature.id }">{{ busyId === feature.id ? '上传中…' : '替换数据源' }}<input type="file" :accept="feature.dataSourceSchema.extensions.join(',')" :disabled="!scopeReady || loading || busyId === feature.id" @change="replaceDataSource(feature, $event)" /></label>
              <button v-if="session.isAdmin" class="text-button feature-config-button" type="button" :disabled="!scopeReady || loading" @click="openConfig(feature)">配置管理</button>
            </div>
          </article>
        </div>
      </Transition>
    </div>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />
    <FeatureConfigDrawer v-if="configFeature" :feature-id="configFeature.id" :feature-name="`${configFeature.customerName} · ${configFeature.name}`" @close="closeConfig" @saved="load" />
    <ModalDialog :open="uploadOpen" title="上传功能包" description="平台只做静态校验和版本登记，不会在 Web 请求中执行包内代码。" width="medium" :closeable="!uploadBusy" @close="closeFeatureUpload">
      <form id="dashboard-feature-upload" class="form-stack" @submit.prevent="submitFeatureUpload">
        <div v-if="session.isAllCustomers" class="field">
          <span>目标客户</span>
          <SearchCombobox v-model="uploadCustomerId" :options="uploadCustomerOptions" placeholder="选择目标客户" search-placeholder="搜索客户…" appearance="form" :disabled="uploadBusy" />
          <small>功能代码作为公共版本保存，配置和数据源仍按所选客户独立管理。</small>
        </div>
        <div v-else class="field">
          <span>目标客户</span>
          <div class="readonly-field">{{ uploadCustomerName }}</div>
        </div>
        <div class="field">
          <span>功能包</span>
          <label class="secondary-button upload-button dashboard-package-picker" :class="{ 'upload-button--disabled': !uploadFormatsReady || uploadFormatsLoading || uploadBusy }">
            {{ uploadFile?.name ?? (uploadFormatsLoading ? '正在读取允许格式…' : uploadFormatsReady ? '选择功能包' : '暂时无法选择功能包') }}
            <input type="file" :accept="uploadAccept" :disabled="!uploadFormatsReady || uploadFormatsLoading || uploadBusy" @change="selectFeaturePackage" />
          </label>
          <small>当前允许：{{ uploadFormatLabel }}。归档根目录必须包含 <code>__init__.py</code>，可以携带 requirements.txt、wheels/ 和默认数据源。</small>
        </div>
        <p v-if="uploadError" class="form-error" role="alert">{{ uploadError }}</p>
      </form>
      <template #footer><button class="secondary-button" type="button" :disabled="uploadBusy" @click="closeFeatureUpload">取消</button><button class="primary-button" type="submit" form="dashboard-feature-upload" :disabled="uploadBusy || uploadFormatsLoading || !uploadFormatsReady || !uploadFile || !uploadCustomerId">{{ uploadBusy ? '正在处理…' : '上传并校验' }}</button></template>
    </ModalDialog>
    <ModalDialog :open="uploadReauthOpen" title="验证管理员身份" description="上传功能代码属于敏感操作，请输入当前登录账号的密码。" width="small" :closeable="!uploadReauthBusy" @close="cancelUploadReauth">
      <form id="dashboard-upload-reauth" class="form-stack" @submit.prevent="confirmUploadReauth"><label class="field"><span>当前密码</span><input v-model="uploadReauthPassword" type="password" autocomplete="current-password" required /></label><p v-if="uploadReauthError" class="form-error" role="alert">{{ uploadReauthError }}</p></form>
      <template #footer><button class="secondary-button" type="button" :disabled="uploadReauthBusy" @click="cancelUploadReauth">取消</button><button class="primary-button" type="submit" form="dashboard-upload-reauth" :disabled="uploadReauthBusy">{{ uploadReauthBusy ? '正在验证…' : '继续上传' }}</button></template>
    </ModalDialog>
  </section>
</template>
