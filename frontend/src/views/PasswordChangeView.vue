<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const busy = ref(false)
const errorMessage = ref('')
const mismatch = computed(() => confirmPassword.value.length > 0 && newPassword.value !== confirmPassword.value)

async function submit(): Promise<void> {
  if (busy.value || mismatch.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await session.changePassword(currentPassword.value, newPassword.value)
    notify.success('密码已更新')
    await router.replace('/')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '密码修改失败'
    notify.error('密码修改失败', { description: errorMessage.value })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">SECURITY</p>
      <h1>设置您自己的密码</h1>
      <p class="auth-subtitle">这是临时密码的首次登录。修改完成前不能进入其他模块。</p>
      <form class="form-stack" @submit.prevent="submit">
        <label class="field"><span>当前临时密码</span><input v-model="currentPassword" type="password" required /></label>
        <label class="field"><span>新密码</span><input v-model="newPassword" type="password" minlength="12" required /></label>
        <label class="field">
          <span>再次输入新密码</span><input v-model="confirmPassword" type="password" required />
          <small v-if="mismatch" class="field-error">两次输入的密码不一致</small>
        </label>
        <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>
        <button class="primary-button primary-button--full" type="submit" :disabled="busy || mismatch">
          {{ busy ? '正在保存…' : '保存并继续' }}
        </button>
      </form>
    </section>
  </main>
</template>
