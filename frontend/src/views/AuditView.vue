<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AnimatedTabs from '@/components/AnimatedTabs.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest } from '@/lib/api'
import type { AuditLog, Paginated, Pagination } from '@/types'

type AuditCategory = 'ADMIN' | 'OPERATOR' | 'AUTH_SYSTEM' | 'ALL'
const logs = ref<AuditLog[]>([])
const loading = ref(true)
const errorMessage = ref('')
const category = ref<AuditCategory>('ADMIN')
const actionFilter = ref('')
const ipFilter = ref('')
const outcomeFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const expandedId = ref<number | null>(null)
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
let requestSequence = 0
const categoryTabs = [
  { value: 'ADMIN', label: '管理员操作' }, { value: 'OPERATOR', label: '普通用户操作' },
  { value: 'AUTH_SYSTEM', label: '登录与系统' }, { value: 'ALL', label: '全部' },
]

onMounted(load)

async function load(): Promise<void> {
  const selectedCategory = category.value
  const sequence = ++requestSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const query = new URLSearchParams({ category: selectedCategory, page: String(pagination.value.page), pageSize: String(pagination.value.pageSize) })
    if (actionFilter.value.trim()) query.set('action', actionFilter.value.trim())
    if (ipFilter.value.trim()) query.set('clientIp', ipFilter.value.trim())
    if (outcomeFilter.value) query.set('outcome', outcomeFilter.value)
    if (dateFrom.value) query.set('from', String(Math.floor(new Date(`${dateFrom.value}T00:00:00`).getTime() / 1000)))
    if (dateTo.value) query.set('to', String(Math.floor(new Date(`${dateTo.value}T23:59:59`).getTime() / 1000)))
    const result = await apiRequest<Paginated<AuditLog>>(`/api/admin/audit-logs?${query}`)
    if (sequence !== requestSequence) return
    logs.value = result.items
    pagination.value = result.pagination
  } catch (error) {
    if (sequence !== requestSequence) return
    errorMessage.value = error instanceof ApiError ? error.message : '审计记录加载失败'
  } finally { if (sequence === requestSequence) loading.value = false }
}

function selectCategory(value: AuditCategory): void {
  category.value = value
  pagination.value.page = 1
  expandedId.value = null
  void load()
}
function selectCategoryValue(value: string): void {
  if (['ADMIN', 'OPERATOR', 'AUTH_SYSTEM', 'ALL'].includes(value)) selectCategory(value as AuditCategory)
}
function applyFilters(): void { pagination.value.page = 1; void load() }
function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; expandedId.value = null; void load() }
function formatTime(value: number): string { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(value * 1000) }
function actionName(action: string): string {
  const names: Record<string, string> = {
    'setup.initialize': '初始化系统', 'auth.login': '账号登录', 'auth.logout': '退出登录',
    'auth.reauthenticate': '敏感操作验证', 'auth.password.change': '修改个人密码',
    'admin.user.create': '创建用户', 'admin.user.update': '修改用户',
    'admin.user.customers.update': '修改客户权限', 'admin.user.password.reset': '重置用户密码',
    'admin.user.sessions.revoke': '撤销用户会话', 'admin.customer.create': '创建客户',
    'admin.customer.update': '修改客户', 'admin.customer_feature.config.view': '查看功能配置',
    'admin.customer_feature.config.update': '修改功能配置', 'customer_feature.data_source.download': '下载数据源',
    'customer_feature.data_source.replace': '替换数据源', 'run.log.download': '下载任务日志',
    'admin.system_log.download': '下载程序日志', 'run.create': '创建运行', 'run.stop': '停止运行',
    'admin.system_update.upload': '上传系统更新包',
    'admin.system_update.apply_requested': '提交系统更新',
    'admin.system_update.retry_created': '重新创建更新尝试',
    'admin.system_update.rollback_requested': '提交系统回退',
    'system.system_update.completed': '系统更新完成',
    'system.system_update.failed': '系统更新失败',
    'system.system_update.automatic_rollback': '更新失败并自动回退',
    'system.system_update.rollback_completed': '系统回退完成',
    'system.system_update.interrupted_rollback': '中断恢复与回退',
    'system.system_update.recovery_failed': '更新恢复失败',
    'system.system_update.handoff_recovered': '恢复更新控制交接',
    'system.system_update.control_rejected': '拒绝异常更新控制文件',
  }
  return names[action] ?? action
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h1>安全审计</h1><p>记录谁在什么时间、从哪个地址、对哪个客户对象执行了什么操作。敏感明文不会写入记录。</p></div><button class="secondary-button" type="button" :disabled="loading" @click="load">刷新</button></div>
    <AnimatedTabs :model-value="category" :options="categoryTabs" aria-label="审计分类" @update:model-value="selectCategoryValue" />
    <Transition name="subpanel" mode="out-in"><div :key="category" class="subpanel-stage">
    <form class="content-card audit-filter-card" @submit.prevent="applyFilters"><label class="field"><span>操作</span><input v-model="actionFilter" placeholder="操作编码关键字" /></label><label class="field"><span>来源 IP</span><input v-model="ipFilter" placeholder="例如 192.168.1" /></label><label class="field"><span>结果</span><select v-model="outcomeFilter"><option value="">全部</option><option value="success">成功</option><option value="denied">拒绝</option><option value="blocked">拦截</option><option value="ignored">忽略</option><option value="failure">失败</option></select></label><label class="field"><span>开始日期</span><input v-model="dateFrom" type="date" /></label><label class="field"><span>结束日期</span><input v-model="dateTo" type="date" /></label><button class="primary-button" type="submit" :disabled="loading">筛选</button></form>
    <p v-if="errorMessage" class="form-error page-error" role="alert">{{ errorMessage }}</p>
    <article class="content-card table-card">
      <div v-if="loading" class="loading-state">正在加载审计记录…</div>
      <div v-else-if="logs.length === 0" class="empty-table">没有符合条件的审计记录。</div>
      <div v-else class="table-scroll"><table><thead><tr><th>时间</th><th>操作</th><th>操作人</th><th>客户 / 对象</th><th>结果</th><th>来源 IP</th><th class="align-right">详情</th></tr></thead><tbody><template v-for="item in logs" :key="item.id"><tr><td class="muted-cell nowrap">{{ formatTime(item.occurredAt) }}</td><td><strong>{{ actionName(item.action) }}</strong><small class="block-copy">{{ item.action }}</small></td><td><strong>{{ item.actorDisplayName ?? '系统/未登录' }}</strong><small class="block-copy">{{ item.actorUsername ? `@${item.actorUsername}` : (item.actorRole ?? '无账号') }}</small></td><td><span>{{ item.customerName ?? '全局操作' }}</span><small class="block-copy">{{ item.targetName ?? item.targetId ?? '—' }}</small></td><td><span class="status-pill" :class="item.outcome === 'success' ? 'status-pill--on' : 'status-pill--warn'">{{ item.outcome === 'success' ? '成功' : item.outcome === 'denied' ? '拒绝' : item.outcome === 'blocked' ? '拦截' : item.outcome === 'ignored' ? '忽略' : '失败' }}</span></td><td class="mono-cell">{{ item.clientIp }}</td><td><div class="row-actions"><button class="text-button" type="button" @click="expandedId = expandedId === item.id ? null : item.id">{{ expandedId === item.id ? '收起' : '查看' }}</button></div></td></tr><tr v-if="expandedId === item.id" class="detail-row"><td colspan="7"><dl class="audit-detail audit-detail--full"><div><dt>操作时间</dt><dd>{{ formatTime(item.occurredAt) }}</dd></div><div><dt>操作账号</dt><dd>{{ item.actorDisplayName ?? '系统/未登录' }} {{ item.actorUsername ? `(@${item.actorUsername})` : '' }} · {{ item.actorRole ?? '无角色快照' }}</dd></div><div><dt>客户</dt><dd>{{ item.customerName ?? '—' }} <span class="mono-cell">{{ item.customerId ?? '' }}</span></dd></div><div><dt>操作对象</dt><dd>{{ item.targetType ?? '—' }} / {{ item.targetName ?? '—' }} / <span class="mono-cell">{{ item.targetId ?? '—' }}</span></dd></div><div><dt>请求</dt><dd><span class="mono-cell">{{ item.requestMethod ?? '—' }} {{ item.requestPath ?? '—' }}</span><br />请求 ID：<span class="mono-cell">{{ item.requestId ?? '—' }}</span></dd></div><div><dt>来源终端</dt><dd>{{ item.clientIp }}<br /><span class="muted-cell">{{ item.userAgent ?? '旧记录未保存终端信息' }}</span></dd></div><div class="audit-detail__payload"><dt>详细数据</dt><dd><pre>{{ JSON.stringify(item.details, null, 2) }}</pre></dd></div></dl></td></tr></template></tbody></table></div>
    </article>
    <PaginationBar v-if="pagination.total > 0" :pagination="pagination" :disabled="loading" @change="changePage" />
    </div></Transition>
  </section>
</template>
