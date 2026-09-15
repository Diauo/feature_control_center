<script setup lang="ts">
import { Eye, EyeOff } from 'lucide'
import { MorphIcon } from 'morphicons/vue'
import { motion, useReducedMotion } from 'motion-v'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import GothicVisualPanel from '@/components/auth/GothicVisualPanel.vue'
import { ApiError } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const username = ref('')
const password = ref('')
const busy = ref(false)
const errorMessage = ref('')
const showPassword = ref(false)
const reduceMotion = useReducedMotion()

async function submit(): Promise<void> {
  if (busy.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await session.login(username.value, password.value)
    await router.replace(session.user?.mustChangePassword ? '/change-password' : '/')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : '登录失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

async function retryConnection(): Promise<void> {
  await session.retryBootstrap()
  if (!session.startupError) notify.success('已恢复与服务器的连接')
  if (session.setupRequired) await router.replace('/setup')
  else if (session.isAuthenticated) await router.replace('/')
}
</script>

<template>
  <main class="login-page">
    <GothicVisualPanel :system-name="session.systemName" />
    <section class="login-form-panel">
      <motion.div
        class="login-form-wrap"
        :initial="reduceMotion ? false : { opacity: 0, x: 12 }"
        :animate="{ opacity: 1, x: 0 }"
        :transition="{ duration: 0.48, delay: 0.06, ease: [0.22, 1, 0.36, 1] }"
      >
        <div class="login-heading">
          <p>{{ session.systemName }}</p>
          <h1>欢迎回来</h1>
          <span>登录后管理您负责的客户和功能。</span>
        </div>
        <div v-if="session.startupError" class="connection-error" role="alert">
          <span>{{ session.startupError }}</span>
          <button class="text-button" type="button" @click="retryConnection">重新连接</button>
        </div>
        <form class="form-stack login-form" @submit.prevent="submit">
          <label class="field">
            <span>用户名</span>
            <input v-model.trim="username" autocomplete="username" autofocus required />
          </label>
          <label class="field">
            <span>密码</span>
            <span class="password-input">
              <input v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required />
              <button type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword">
                <MorphIcon :icon="showPassword ? EyeOff : Eye" :size="18" reduced-motion="user" aria-hidden="true" />
              </button>
            </span>
          </label>
          <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
          <button class="primary-button primary-button--full login-submit" type="submit" :disabled="busy">
            <span v-if="busy" class="button-spinner" aria-hidden="true"></span>
            {{ busy ? '正在登录…' : '登录' }}
          </button>
        </form>
        <p class="auth-footnote">没有公开注册入口。账号由系统管理员统一创建。</p>
      </motion.div>
    </section>
  </main>
</template>
