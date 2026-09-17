<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import AnimatedTabs from '@/components/AnimatedTabs.vue'
import ModalDialog from '@/components/ModalDialog.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import { ApiError, apiRequest } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { Customer, MenuKey, Paginated, Pagination, UserRole, UserSummary } from '@/types'

interface UserForm {
  username: string
  displayName: string
  role: UserRole
  isActive: boolean
  customerIds: string[]
  menuKeys: MenuKey[]
}

const session = useSessionStore()
const users = ref<UserSummary[]>([])
const customers = ref<Customer[]>([])
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref('')
const createOpen = ref(false)
const editOpen = ref(false)
const editingId = ref<string | null>(null)
const reauthOpen = ref(false)
const reauthPassword = ref('')
const reauthError = ref('')
const temporaryPassword = ref('')
const temporaryOwner = ref('')
const deleteTarget = ref<UserSummary | null>(null)
const deletePassword = ref('')
const deleteError = ref('')

function openDeleteUser(user: UserSummary): void {
  deleteTarget.value = user
  deletePassword.value = ''
  deleteError.value = ''
}

function closeDeleteUser(): void {
  if (busy.value) return
  deleteTarget.value = null
  deletePassword.value = ''
  deleteError.value = ''
}
const copied = ref(false)
const activeRole = ref<UserRole>('operator')
const pagination = ref<Pagination>({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
let pendingAction: (() => Promise<void>) | null = null
let requestSequence = 0

const emptyForm = (): UserForm => ({
  username: '',
  displayName: '',
  role: 'operator',
  isActive: true,
  customerIds: [],
  menuKeys: ['workspace', 'runs'],
})
const form = ref<UserForm>(emptyForm())
const editingUser = computed(() => users.value.find((user) => user.id === editingId.value) ?? null)
const visibleUsers = computed(() => users.value)
const roleTabs = computed(() => [
  { value: 'operator', label: '业务用户', count: activeRole.value === 'operator' ? pagination.value.total : undefined },
  { value: 'admin', label: '系统管理员', count: activeRole.value === 'admin' ? pagination.value.total : undefined },
])
const menuCatalog: Array<{ key: MenuKey; label: string }> = [
  { key: 'workspace', label: '工作台' },
  { key: 'runs', label: '运行记录' },
  { key: 'schedules', label: '定时任务' },
  { key: 'feature_admin', label: '功能管理' },
  { key: 'users', label: '用户管理' },
  { key: 'customers', label: '客户管理' },
  { key: 'audit', label: '安全审计' },
]
const menuLabels = new Map<MenuKey, string>(menuCatalog.map((item) => [item.key, item.label]))

onMounted(load)

async function load(): Promise<void> {
  const role = activeRole.value
  const sequence = ++requestSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const [userResult, customerResult] = await Promise.all([
      apiRequest<Paginated<UserSummary>>(`/api/admin/users?role=${role}&page=${pagination.value.page}&pageSize=${pagination.value.pageSize}`),
      apiRequest<{ items: Customer[] }>('/api/customers'),
    ])
    if (sequence !== requestSequence) return
    users.value = userResult.items
    pagination.value = userResult.pagination
    customers.value = customerResult.items
  } catch (error) {
    if (sequence !== requestSequence) return
    errorMessage.value = readableError(error, '用户数据加载失败')
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function changePage(page: number, pageSize: number): void { pagination.value = { ...pagination.value, page, pageSize }; void load() }
watch(activeRole, () => { pagination.value.page = 1; void load() })
function selectRole(value: string): void { if (value === 'admin' || value === 'operator') activeRole.value = value }

function openCreate(): void {
  errorMessage.value = ''
  form.value = emptyForm()
  form.value.role = activeRole.value
  createOpen.value = true
}

function openEdit(user: UserSummary): void {
  errorMessage.value = ''
  editingId.value = user.id
  form.value = {
    username: user.username,
    displayName: user.displayName,
    role: user.role,
    isActive: user.isActive ?? true,
    customerIds: [...(user.customerIds ?? [])],
    menuKeys: [...(user.menuKeys ?? [])],
  }
  editOpen.value = true
}

async function createUser(): Promise<void> {
  await runSensitive(async () => {
    busy.value = true
    try {
      const result = await apiRequest<{ user: UserSummary; temporaryPassword: string }>('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: form.value.username,
          displayName: form.value.displayName,
          role: form.value.role,
          customerIds: form.value.role === 'operator' ? form.value.customerIds : [],
          menuKeys: form.value.role === 'operator' ? form.value.menuKeys : [],
        }),
      })
      temporaryPassword.value = result.temporaryPassword
      temporaryOwner.value = result.user.displayName
      copied.value = false
      createOpen.value = false
      await load()
      notify.success('用户已创建', { description: `${result.user.displayName} 的临时密码已生成` })
    } finally {
      busy.value = false
    }
  })
}

async function saveUser(): Promise<void> {
  const userId = editingId.value
  if (!userId) return
  await runSensitive(async () => {
    busy.value = true
    try {
      const result = await apiRequest<{ user: UserSummary }>(`/api/admin/users/${userId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          displayName: form.value.displayName,
          role: form.value.role,
          isActive: form.value.isActive,
          customerIds: form.value.role === 'operator' ? form.value.customerIds : [],
          menuKeys: form.value.role === 'operator' ? form.value.menuKeys : [],
        }),
      })
      replaceUser(result.user)
      editOpen.value = false
      await session.reloadCustomers()
      notify.success('用户信息已更新', { description: result.user.displayName })
    } finally {
      busy.value = false
    }
  })
}

async function resetPassword(user: UserSummary): Promise<void> {
  if (!window.confirm(`确定为“${user.displayName}”生成新的临时密码吗？该用户现有登录会立即失效。`)) return
  await runSensitive(async () => {
    busy.value = true
    try {
      const result = await apiRequest<{ temporaryPassword: string }>(
        `/api/admin/users/${user.id}/reset-password`,
        { method: 'POST' },
      )
      temporaryPassword.value = result.temporaryPassword
      temporaryOwner.value = user.displayName
      copied.value = false
      errorMessage.value = ''
      await load()
      notify.success('临时密码已重置', { description: `${user.displayName} 的现有会话已失效` })
    } finally {
      busy.value = false
    }
  })
}

async function deleteUser(user: UserSummary): Promise<void> {
  if (!deletePassword.value) {
    deleteError.value = '请输入当前登录账号的密码'
    return
  }
  busy.value = true
  deleteError.value = ''
  try {
    await session.reauthenticate(deletePassword.value)
  } catch (reason) {
    deleteError.value = reason instanceof ApiError ? reason.message : '密码验证失败，请重试'
    busy.value = false
    return
  }
  try {
    await apiRequest(`/api/admin/users/${user.id}`, { method: 'DELETE' })
    deleteTarget.value = null
    deletePassword.value = ''
    await load()
    notify.success('用户已删除', { description: `${user.displayName} · 历史审计记录保留` })
  } catch (reason) {
    deleteError.value = reason instanceof ApiError ? reason.message : '删除失败，请稍后重试'
    notify.error('删除失败', { description: deleteError.value })
  } finally {
    busy.value = false
  }
}

async function revokeSessions(user: UserSummary): Promise<void> {
  if (!window.confirm(`确定让“${user.displayName}”的所有登录会话立即退出吗？`)) return
  await runSensitive(async () => {
    busy.value = true
    try {
      await apiRequest(`/api/admin/users/${user.id}/revoke-sessions`, { method: 'POST' })
      notify.success('用户会话已撤销', { description: user.displayName })
    } finally {
      busy.value = false
    }
  })
}

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
    errorMessage.value = readableError(error, '操作失败，请稍后重试')
    notify.error('用户操作失败', { description: errorMessage.value })
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

async function copyTemporaryPassword(): Promise<void> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(temporaryPassword.value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = temporaryPassword.value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const succeeded = document.execCommand('copy')
      textarea.remove()
      if (!succeeded) throw new Error('copy failed')
    }
    copied.value = true
    notify.success('临时密码已复制')
  } catch {
    errorMessage.value = '浏览器未允许自动复制，请手动选择并保存临时密码。'
    notify.warning('无法自动复制', { description: errorMessage.value })
  }
}

function replaceUser(user: UserSummary): void {
  const index = users.value.findIndex((item) => item.id === user.id)
  if (index >= 0) users.value[index] = user
}

function customerNames(user: UserSummary): string {
  if (user.role === 'admin') return '管理员可管理全部客户'
  const ids = new Set(user.customerIds ?? [])
  const names = customers.value.filter((customer) => ids.has(customer.id)).map((customer) => customer.name)
  return names.join('、') || '未分配客户'
}

function menuNames(user: UserSummary): string {
  const keys = user.menuKeys ?? []
  return keys.map((key) => menuLabels.get(key) ?? key).join('、') || '未授权'
}

function formatTime(value?: number | null): string {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(value * 1000) : '从未登录'
}

function readableError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <h1>用户管理</h1>
        <p>业务操作员按客户与菜单授权；系统管理员拥有全部权限。</p>
      </div>
      <button class="primary-button" type="button" @click="openCreate">{{ activeRole === 'admin' ? '添加系统管理员' : '添加业务用户' }}</button>
    </div>

    <AnimatedTabs :model-value="activeRole" :options="roleTabs" aria-label="用户类型" @update:model-value="selectRole" />

    <p v-if="errorMessage" class="form-error page-error" role="alert">{{ errorMessage }}</p>
    <Transition name="subpanel" mode="out-in"><div :key="activeRole" class="subpanel-stage">
    <article class="content-card table-card">
      <div v-if="loading" class="loading-state">正在加载用户…</div>
      <div v-else-if="visibleUsers.length === 0" class="empty-table">{{ activeRole === 'admin' ? '尚无其他系统管理员。' : '尚未创建业务用户。' }}</div>
      <div v-else class="table-scroll">
        <table>
          <thead><tr><th>用户</th><th v-if="activeRole === 'operator'">客户范围</th><th v-if="activeRole === 'operator'">菜单权限</th><th>最近登录</th><th>状态</th><th class="align-right">操作</th></tr></thead>
          <tbody>
            <tr v-for="user in visibleUsers" :key="user.id">
              <td><div class="identity-cell"><span class="mini-avatar">{{ user.displayName.slice(0, 1) }}</span><span><strong>{{ user.displayName }}</strong><small>@{{ user.username }}</small></span></div></td>
              <td v-if="activeRole === 'operator'" class="muted-cell">{{ customerNames(user) }}</td>
              <td v-if="activeRole === 'operator'" class="muted-cell">{{ menuNames(user) }}</td>
              <td class="muted-cell">{{ formatTime(user.lastLoginAt) }}</td>
              <td><span class="status-pill" :class="user.isActive === false ? 'status-pill--off' : 'status-pill--on'">{{ user.isActive === false ? '已停用' : '正常' }}</span></td>
              <td><div class="row-actions"><button class="text-button" type="button" @click="openEdit(user)">编辑</button><button v-if="user.id !== session.user?.id" class="text-button" type="button" :disabled="busy" @click="resetPassword(user)">重置密码</button><button v-if="user.id !== session.user?.id" class="text-button" type="button" :disabled="busy" @click="revokeSessions(user)">退出会话</button><button v-if="user.role === 'operator' && user.id !== session.user?.id" class="text-button text-button--danger" type="button" :disabled="busy" @click="openDeleteUser(user)">删除</button></div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
    <PaginationBar v-if="pagination.total > 20" :pagination="pagination" :disabled="loading" @change="changePage" />
    </div></Transition>

    <ModalDialog :open="createOpen" :title="form.role === 'admin' ? '添加系统管理员' : '添加业务用户'" description="系统只显示一次临时密码，请及时交给对应人员。" @close="createOpen = false">
      <form id="create-user-form" class="form-grid" @submit.prevent="createUser">
        <label class="field"><span>用户名</span><input v-model.trim="form.username" autocomplete="off" minlength="3" maxlength="64" required /></label>
        <label class="field"><span>显示名称</span><input v-model.trim="form.displayName" maxlength="64" required /></label>
        <div class="field"><span>账号类型</span><div class="readonly-field">{{ form.role === 'admin' ? '系统管理员' : '业务操作员' }}</div></div>
        <div v-if="form.role === 'operator'" class="field field--wide"><span>菜单权限</span><div class="check-grid"><label v-for="item in menuCatalog" :key="item.key" class="check-item"><input v-model="form.menuKeys" type="checkbox" :value="item.key" /><span>{{ item.label }}</span></label><small>「系统设置」仅管理员可用，业务员至少勾选一项。</small></div></div>
        <div v-if="form.role === 'operator'" class="field field--wide"><span>可管理客户</span><div class="check-grid"><label v-for="customer in customers.filter((item) => item.isActive)" :key="customer.id" class="check-item"><input v-model="form.customerIds" type="checkbox" :value="customer.id" /><span>{{ customer.name }}</span></label><small v-if="customers.filter((item) => item.isActive).length === 0">请先创建客户。</small></div></div><p v-if="errorMessage" class="form-error field--wide" role="alert">{{ errorMessage }}</p>
      </form>
      <template #footer><button class="secondary-button" type="button" @click="createOpen = false">取消</button><button class="primary-button" type="submit" form="create-user-form" :disabled="busy || (form.role === 'operator' && form.menuKeys.length === 0)">{{ busy ? '正在创建…' : '创建用户' }}</button></template>
    </ModalDialog>

    <ModalDialog :open="editOpen" title="编辑用户" :description="editingUser ? `正在编辑 @${editingUser.username}` : ''" @close="editOpen = false">
      <form id="edit-user-form" class="form-grid" @submit.prevent="saveUser">
        <label class="field"><span>用户名</span><input :value="form.username" disabled /></label>
        <label class="field"><span>显示名称</span><input v-model.trim="form.displayName" maxlength="64" required /></label>
        <div class="field"><span>账号类型</span><div class="readonly-field">{{ form.role === 'admin' ? '系统管理员' : '业务操作员' }}</div></div>
        <label class="field toggle-field"><span><strong>允许登录</strong><small>停用后该用户的现有会话会立即失效。</small></span><input v-model="form.isActive" class="switch" type="checkbox" :disabled="editingId === session.user?.id" /></label>
        <div v-if="form.role === 'operator'" class="field field--wide"><span>菜单权限</span><div class="check-grid"><label v-for="item in menuCatalog" :key="item.key" class="check-item"><input v-model="form.menuKeys" type="checkbox" :value="item.key" /><span>{{ item.label }}</span></label><small>「系统设置」仅管理员可用，业务员至少勾选一项。</small></div></div>
        <div v-if="form.role === 'operator'" class="field field--wide"><span>可管理客户</span><div class="check-grid"><label v-for="customer in customers.filter((item) => item.isActive)" :key="customer.id" class="check-item"><input v-model="form.customerIds" type="checkbox" :value="customer.id" /><span>{{ customer.name }}</span></label></div></div><p v-if="errorMessage" class="form-error field--wide" role="alert">{{ errorMessage }}</p>
      </form>
      <template #footer><button class="secondary-button" type="button" @click="editOpen = false">取消</button><button class="primary-button" type="submit" form="edit-user-form" :disabled="busy || (form.role === 'operator' && form.menuKeys.length === 0)">{{ busy ? '正在保存…' : '保存修改' }}</button></template>
    </ModalDialog>

    <ModalDialog :open="Boolean(deleteTarget)" title="删除用户" :description="deleteTarget ? `即将删除 @${deleteTarget.username}` : ''" width="small" :closeable="!busy" @close="closeDeleteUser">
      <div class="form-stack">
        <p class="notice-copy">删除后该账号将无法登录，其登录会话立即失效。</p>
        <p class="notice-copy">该操作不可撤销；历史审计记录会保留账号快照。</p>
        <label class="field"><span>当前登录账号的密码</span><input v-model="deletePassword" type="password" autocomplete="current-password" :disabled="busy" /></label>
        <p class="notice-copy">使用你登录本系统的账号密码确认（管理员与业务员都用本人密码）。</p>
        <p v-if="deleteError" class="form-error" role="alert">{{ deleteError }}</p>
      </div>
      <template #footer><button class="secondary-button" type="button" :disabled="busy" @click="closeDeleteUser">取消</button><button class="danger-button" type="button" :disabled="busy" @click="deleteTarget && deleteUser(deleteTarget)">{{ busy ? '正在验证并删除…' : '确认删除' }}</button></template>
    </ModalDialog>

    <ModalDialog :open="reauthOpen" title="验证身份" description="这是敏感操作，请输入当前登录账号的密码。" :closeable="!busy" width="small" @close="cancelReauthentication">
      <form id="reauth-form" class="form-stack" @submit.prevent="confirmReauthentication"><label class="field"><span>当前密码</span><input v-model="reauthPassword" type="password" autocomplete="current-password" autofocus required /></label><p v-if="reauthError" class="form-error" role="alert">{{ reauthError }}</p></form>
      <template #footer><button class="secondary-button" type="button" :disabled="busy" @click="cancelReauthentication">取消</button><button class="primary-button" type="submit" form="reauth-form" :disabled="busy">{{ busy ? '正在验证…' : '继续' }}</button></template>
    </ModalDialog>

    <ModalDialog :open="Boolean(temporaryPassword)" title="临时密码已生成" :description="`请将下面的密码安全地交给 ${temporaryOwner}。关闭后无法再次查看。`" :closeable="false" width="small">
      <div class="secret-panel"><code>{{ temporaryPassword }}</code><button class="secondary-button" type="button" @click="copyTemporaryPassword">{{ copied ? '已复制' : '复制' }}</button></div><p v-if="errorMessage" class="form-error secret-error" role="alert">{{ errorMessage }}</p><p class="notice-copy">该用户首次登录后必须先修改密码，之后才能操作其他功能。</p>
      <template #footer><button class="primary-button" type="button" @click="temporaryPassword = ''">我已保存，关闭</button></template>
    </ModalDialog>
  </section>
</template>
