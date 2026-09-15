import { createRouter, createWebHistory } from 'vue-router'

import { useSessionStore } from '@/stores/session'
import AppShell from '@/components/AppShell.vue'
import AuditView from '@/views/AuditView.vue'
import CustomersView from '@/views/CustomersView.vue'
import FeatureVersionsView from '@/views/FeatureVersionsView.vue'
import HomeView from '@/views/HomeView.vue'
import LoginView from '@/views/LoginView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import PasswordChangeView from '@/views/PasswordChangeView.vue'
import RunDetailView from '@/views/RunDetailView.vue'
import RunsView from '@/views/RunsView.vue'
import SchedulesView from '@/views/SchedulesView.vue'
import SetupView from '@/views/SetupView.vue'
import SettingsView from '@/views/SettingsView.vue'
import UsersView from '@/views/UsersView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return to.path === from.path ? false : { top: 0 }
  },
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/setup', component: SetupView, meta: { public: true } },
    { path: '/change-password', component: PasswordChangeView },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', component: HomeView },
        { path: 'runs', component: RunsView },
        { path: 'runs/:requestId', component: RunDetailView },
        { path: 'schedules', component: SchedulesView },
        { path: 'admin/users', component: UsersView, meta: { admin: true } },
        { path: 'admin/customers', component: CustomersView, meta: { admin: true } },
        { path: 'admin/features', component: FeatureVersionsView, meta: { admin: true } },
        {
          path: 'admin/features/:featureId/config',
          redirect: (to) => ({ path: '/', query: { config: String(to.params.featureId) } }),
          meta: { admin: true },
        },
        { path: 'admin/settings', component: SettingsView, meta: { admin: true } },
        { path: 'admin/audit', component: AuditView, meta: { admin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  await session.bootstrap()
  if (session.setupRequired && to.path !== '/setup') return '/setup'
  if (!session.setupRequired && to.path === '/setup') return session.isAuthenticated ? '/' : '/login'
  if (!to.meta.public && !session.isAuthenticated) return '/login'
  if (session.isAuthenticated && to.path === '/login') return '/'
  if (session.user?.mustChangePassword && to.path !== '/change-password') return '/change-password'
  if (to.meta.admin && !session.isAdmin) return '/'
  return true
})
