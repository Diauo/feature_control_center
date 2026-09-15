import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import { router } from '@/router'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import 'vue-sonner/style.css'
import '@/styles.css'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia).use(router)

const session = useSessionStore(pinia)
window.addEventListener('fcc:auth-expired', () => {
  if (!session.isAuthenticated) return
  session.clearSession()
  notify.warning('登录状态已失效', { description: '请重新登录后继续操作。' })
  void router.replace('/login')
})

app.mount('#app')
