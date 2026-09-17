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
import type { MenuKey } from '@/types'

const menuFallbackOrder: Array<{ menu: MenuKey; path: string }> = [
  { menu: 'workspace', path: '/' },
  { menu: 'runs', path: '/runs' },
  { menu: 'schedules', path: '/schedules' },
  { menu: 'feature_admin', path: '/admin/features' },
  { menu: 'users', path: '/admin/users' },
  { menu: 'customers', path: '/admin/customers' },
  { menu: 'audit', path: '/admin/audit' },
  { menu: 'settings', path: '/admin/settings' },
]

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
        { path: '', component: HomeView, meta: { menu: 'workspace' } },
        { path: 'runs', component: RunsView, meta: { menu: 'runs' } },
        { path: 'runs/:requestId', component: RunDetailView, meta: { menu: 'runs' } },
        { path: 'schedules', component: SchedulesView, meta: { menu: 'schedules' } },
        { path: 'admin/users', component: UsersView, meta: { menu: 'users' } },
        { path: 'admin/customers', component: CustomersView, meta: { menu: 'customers' } },
        { path: 'admin/features', component: FeatureVersionsView, meta: { menu: 'feature_admin' } },
        {
          path: 'admin/features/:featureId/config',
          redirect: (to) => ({ path: '/admin/features', query: { config: String(to.params.featureId) } }),
          meta: { menu: 'feature_admin' },
        },
        { path: 'admin/settings', component: SettingsView, meta: { menu: 'settings' } },
        { path: 'admin/audit', component: AuditView, meta: { menu: 'audit' } },
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
  const menu = to.meta.menu as MenuKey | undefined
  if (menu && !session.hasMenu(menu)) {
    const fallback = menuFallbackOrder.find((entry) => session.hasMenu(entry.menu))
    if (fallback && fallback.path !== to.path) return fallback.path
  }
  return true
})
