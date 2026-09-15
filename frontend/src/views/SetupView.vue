<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/lib/api'
import { apiRequest } from '@/lib/api'
import SearchCombobox from '@/components/SearchCombobox.vue'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const form = ref({
  bootstrapCode: '',
  systemName: '功能控制中心',
  adminUsername: 'admin',
  adminDisplayName: '系统管理员',
  password: '',
  confirmPassword: '',
  customerName: '',
  systemTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Hong_Kong',
})
const timezones = ref<string[]>([])
const serverTimezone = ref('UTC')
const busy = ref(false)
const errorMessage = ref('')
const passwordMismatch = computed(
  () => form.value.confirmPassword.length > 0 && form.value.password !== form.value.confirmPassword,
)
const timezoneOptions = computed(() => timezones.value.map((value) => ({ value, label: value, description: value === serverTimezone.value ? '服务器检测' : undefined })))

onMounted(async () => {
  try {
    const result = await apiRequest<{ items: string[]; serverDetected: string }>('/api/setup/timezones')
    timezones.value = result.items
    serverTimezone.value = result.serverDetected
  } catch {
    timezones.value = [form.value.systemTimezone]
  }
})

async function submit(): Promise<void> {
  if (busy.value || passwordMismatch.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await session.initializeSystem({
      bootstrapCode: form.value.bootstrapCode,
      systemName: form.value.systemName,
      adminUsername: form.value.adminUsername,
      adminDisplayName: form.value.adminDisplayName,
      password: form.value.password,
      customerName: form.value.customerName,
      systemTimezone: form.value.systemTimezone,
    })
    notify.success('系统初始化完成')
    await router.replace('/')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '初始化失败，请检查后重试'
    notify.error('系统初始化失败', { description: errorMessage.value })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-page auth-page--setup">
    <section class="auth-card auth-card--wide">
      <p class="eyebrow">FIRST RUN</p>
      <h1>初始化功能控制中心</h1>
      <p class="auth-subtitle">
        初始化码位于交付目录的 <code>data/first-run.txt</code>。完成后该文件会自动删除。
      </p>
      <form class="form-grid" @submit.prevent="submit">
        <label class="field field--wide">
          <span>一次性初始化码</span>
          <input v-model.trim="form.bootstrapCode" autocomplete="one-time-code" required />
        </label>
        <label class="field">
          <span>系统名称</span>
          <input v-model.trim="form.systemName" required maxlength="80" />
        </label>
        <label class="field">
          <span>首个客户</span>
          <input v-model.trim="form.customerName" required maxlength="120" placeholder="例如：A客户" />
        </label>
        <label class="field field--wide">
          <span>系统时区</span>
          <SearchCombobox v-model="form.systemTimezone" :options="timezoneOptions" search-placeholder="搜索 IANA 时区…" />
          <small>默认使用浏览器时区；服务器检测为 {{ serverTimezone || '未可靠检测' }}。</small>
        </label>
        <label class="field">
          <span>管理员用户名</span>
          <input v-model.trim="form.adminUsername" autocomplete="username" required minlength="3" maxlength="64" />
        </label>
        <label class="field">
          <span>管理员显示名称</span>
          <input v-model.trim="form.adminDisplayName" required maxlength="64" />
        </label>
        <label class="field">
          <span>管理员密码</span>
          <input v-model="form.password" type="password" autocomplete="new-password" required minlength="12" />
          <small>至少 12 个字符，可以使用密码短语。</small>
        </label>
        <label class="field">
          <span>再次输入密码</span>
          <input v-model="form.confirmPassword" type="password" autocomplete="new-password" required />
          <small v-if="passwordMismatch" class="field-error">两次输入的密码不一致</small>
        </label>
        <p v-if="errorMessage" class="form-error field--wide" role="alert">{{ errorMessage }}</p>
        <div class="form-actions field--wide">
          <button class="primary-button" type="submit" :disabled="busy || passwordMismatch">
            {{ busy ? '正在初始化…' : '创建系统' }}
          </button>
        </div>
      </form>
    </section>
  </main>
</template>
