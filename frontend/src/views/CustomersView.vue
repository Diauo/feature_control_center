<script setup lang="ts">
import { onMounted, ref } from 'vue'

import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { Customer, Paginated, Pagination } from '@/types'

const session = useSessionStore()
const customers = ref<Customer[]>([])
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref('')
const modalOpen = ref(false)
const editingId = ref<string | null>(null)
const form = ref({ name: '', description: '', isActive: true })
const reauthOpen = ref(false)
const reauthPassword = ref('')
const reauthError = ref('')
let pendingAction: (() => Promise<void>) | null = null
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await apiRequest<Paginated<Customer>>(`/api/admin/customers?page=${pagination.value.page}&pageSize=${pagination.value.pageSize}`)
    customers.value = result.items
    pagination.value = result.pagination
  } catch (error) {
    errorMessage.value = readableError(error, '客户数据加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  errorMessage.value = ''
  editingId.value = null
  form.value = { name: '', description: '', isActive: true }
  modalOpen.value = true
}

function openEdit(customer: Customer): void {
  errorMessage.value = ''
  editingId.value = customer.id
  form.value = { name: customer.name, description: customer.description, isActive: customer.isActive }
  modalOpen.value = true
}

async function save(): Promise<void> {
  if (busy.value) return
  await runSensitive(async () => {
    busy.value = true
    const wasEditing = Boolean(editingId.value)
    try {
      if (editingId.value) {
        const result = await apiRequest<{ customer: Customer }>(`/api/admin/customers/${editingId.value}`, {
          method: 'PATCH',
          body: JSON.stringify(form.value),
        })
        const index = customers.value.findIndex((customer) => customer.id === result.customer.id)
        if (index >= 0) customers.value[index] = result.customer
      } else {
        const result = await apiRequest<{ customer: Customer }>('/api/admin/customers', {
          method: 'POST',
          body: JSON.stringify({ name: form.value.name, description: form.value.description }),
        })
        customers.value.push(result.customer)
      }
      modalOpen.value = false
      await session.reloadCustomers()
      await load()
      notify.success(wasEditing ? '客户信息已更新' : '客户已创建', { description: form.value.name })
    } finally {
      busy.value = false
    }
  })
}

function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }

async function runSensitive(action: () => Promise<void>): Promise<void> {
  errorMessage.value = ''
  try {
    await action()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'REAUTHENTICATION_REQUIRED') {
      pendingAction = action
      reauthPassword.value = ''
      reauthError.value = ''
      reauthOpen.value = true
      return
    }
    errorMessage.value = readableError(error, '客户保存失败')
    notify.error('客户保存失败', { description: errorMessage.value })
  }
}

async function confirmReauthentication(): Promise<void> {
  if (busy.value || !pendingAction) return
  busy.value = true
  reauthError.value = ''
  try {
    await session.reauthenticate(reauthPassword.value)
    const action = pendingAction
    pendingAction = null
    reauthOpen.value = false
    busy.value = false
    await runSensitive(action)
  } catch (error) {
    reauthError.value = readableError(error, '密码验证失败')
  } finally {
    busy.value = false
  }
}

function cancelReauthentication(): void {
  pendingAction = null
  reauthOpen.value = false
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(value * 1000)
}

function readableError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}
</script>

<template>
  <section>
    <div class="page-heading"><div><h1>客户管理</h1><p>客户是功能、配置、数据源、日志与定时任务的业务边界。</p></div><button class="primary-button" type="button" @click="openCreate">添加客户</button></div>
    <p v-if="errorMessage" class="form-error page-error" role="alert">{{ errorMessage }}</p>
    <article class="content-card table-card">
      <div v-if="loading" class="loading-state">正在加载客户…</div>
      <div v-else-if="customers.length === 0" class="empty-table">尚未创建客户。</div>
      <div v-else class="table-scroll"><table><thead><tr><th>客户</th><th>说明</th><th>创建日期</th><th>状态</th><th class="align-right">操作</th></tr></thead><tbody><tr v-for="customer in customers" :key="customer.id"><td><strong>{{ customer.name }}</strong></td><td class="muted-cell">{{ customer.description || '—' }}</td><td class="muted-cell">{{ formatDate(customer.createdAt) }}</td><td><span class="status-pill" :class="customer.isActive ? 'status-pill--on' : 'status-pill--off'">{{ customer.isActive ? '正常' : '已停用' }}</span></td><td><div class="row-actions"><button class="text-button" type="button" @click="openEdit(customer)">编辑</button></div></td></tr></tbody></table></div>
    </article>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />
    <article class="info-card"><span class="info-symbol">i</span><div><strong>停用不会删除历史数据</strong><p>停用客户后，普通用户不能再切换到该客户；已有功能、配置和日志会保留，便于后续恢复和审计。</p></div></article>

    <ModalDialog :open="modalOpen" :title="editingId ? '编辑客户' : '添加客户'" description="客户名称用于全站切换和归属标识，请使用业务人员熟悉的名称。" @close="modalOpen = false">
      <form id="customer-form" class="form-stack" @submit.prevent="save"><label class="field"><span>客户名称</span><input v-model.trim="form.name" maxlength="120" required /></label><label class="field"><span>说明</span><textarea v-model.trim="form.description" rows="4" maxlength="500" placeholder="可选，例如所属区域或对接负责人"></textarea></label><label v-if="editingId" class="field toggle-field"><span><strong>启用客户</strong><small>停用后不会删除客户下的历史内容。</small></span><input v-model="form.isActive" class="switch" type="checkbox" /></label><p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p></form>
      <template #footer><button class="secondary-button" type="button" @click="modalOpen = false">取消</button><button class="primary-button" type="submit" form="customer-form" :disabled="busy">{{ busy ? '正在保存…' : '保存' }}</button></template>
    </ModalDialog>
    <ModalDialog :open="reauthOpen" title="验证管理员身份" description="这是敏感操作，请输入当前登录账号的密码。" :closeable="!busy" width="small" @close="cancelReauthentication"><form id="customer-reauth-form" class="form-stack" @submit.prevent="confirmReauthentication"><label class="field"><span>当前密码</span><input v-model="reauthPassword" type="password" autocomplete="current-password" autofocus required /></label><p v-if="reauthError" class="form-error" role="alert">{{ reauthError }}</p></form><template #footer><button class="secondary-button" type="button" :disabled="busy" @click="cancelReauthentication">取消</button><button class="primary-button" type="submit" form="customer-reauth-form" :disabled="busy">{{ busy ? '正在验证…' : '继续' }}</button></template></ModalDialog>
  </section>
</template>
