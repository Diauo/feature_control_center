<script setup lang="ts">
import {
  Building2,
  CalendarClock,
  History,
  LayoutDashboard,
  LibraryBig,
  Settings,
  ShieldCheck,
  Users,
} from '@lucide/vue'
import { PanelLeftClose, PanelLeftOpen } from 'lucide'
import { MorphIcon } from 'morphicons/vue'
import { TooltipContent, TooltipPortal, TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SearchCombobox from '@/components/SearchCombobox.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const mobileNavOpen = ref(false)
const collapsed = ref(window.localStorage.getItem('fcc.sidebar.collapsed') === 'true')
const sidebarTransitioning = ref(false)
const openTooltipKey = ref<string | null>(null)
let transitionTimer: number | undefined

const insecure = computed(() => window.location.protocol !== 'https:')
const customerOptions = computed(() => [
  { value: '__all__', label: '全部客户', description: `查看有权访问的 ${session.customers.length} 个客户` },
  ...session.customers.map((customer) => ({ value: customer.id, label: customer.name })),
])
const navCatalog = [
  { label: '工作台', path: '/', menu: 'workspace', icon: LayoutDashboard },
  { label: '运行记录', path: '/runs', menu: 'runs', icon: History },
  { label: '定时任务', path: '/schedules', menu: 'schedules', icon: CalendarClock },
  { label: '功能管理', path: '/admin/features', menu: 'feature_admin', icon: LibraryBig },
  { label: '用户管理', path: '/admin/users', menu: 'users', icon: Users },
  { label: '客户管理', path: '/admin/customers', menu: 'customers', icon: Building2 },
  { label: '安全审计', path: '/admin/audit', menu: 'audit', icon: ShieldCheck },
  { label: '系统设置', path: '/admin/settings', menu: 'settings', icon: Settings },
] as const
const navItems = computed(() => navCatalog.filter((item) => session.hasMenu(item.menu)))

async function signOut(): Promise<void> {
  await session.logout()
  await router.replace('/login')
}

function navigate(path: string): void {
  openTooltipKey.value = null
  mobileNavOpen.value = false
  void router.push(path)
}

function toggleSidebar(): void {
  openTooltipKey.value = null
  collapsed.value = !collapsed.value
  sidebarTransitioning.value = true
  window.clearTimeout(transitionTimer)
  transitionTimer = window.setTimeout(() => { sidebarTransitioning.value = false }, 300)
  window.localStorage.setItem('fcc.sidebar.collapsed', String(collapsed.value))
}

function updateTooltip(key: string, open: boolean): void {
  if (!collapsed.value || sidebarTransitioning.value || !open) {
    if (openTooltipKey.value === key) openTooltipKey.value = null
    return
  }
  openTooltipKey.value = key
}

function finishSidebarTransition(event: TransitionEvent): void {
  if (event.propertyName !== 'width') return
  window.clearTimeout(transitionTimer)
  sidebarTransitioning.value = false
}

onBeforeUnmount(() => window.clearTimeout(transitionTimer))
</script>

<template>
  <TooltipProvider :delay-duration="280">
    <div class="app-shell" :class="{ 'app-shell--collapsed': collapsed }">
      <aside class="sidebar" :class="{ 'sidebar--open': mobileNavOpen, 'sidebar--collapsed': collapsed, 'sidebar--transitioning': sidebarTransitioning }" @mouseleave="openTooltipKey = null" @transitionend="finishSidebarTransition">
        <div class="brand">
          <strong>{{ session.systemName }}</strong>
        </div>

        <nav class="navigation" aria-label="主导航">
          <TooltipRoot v-for="item in navItems" :key="item.path" :open="openTooltipKey === item.path" @update:open="updateTooltip(item.path, $event)">
            <TooltipTrigger as-child>
              <button
                class="nav-item"
                :class="{ 'nav-item--active': route.path === item.path || (item.path !== '/' && route.path.startsWith(`${item.path}/`)) }"
                type="button"
                :aria-label="item.label"
                @click="navigate(item.path)"
              >
                <component :is="item.icon" class="nav-item__icon" :size="19" aria-hidden="true" />
                <span>{{ item.label }}</span>
              </button>
            </TooltipTrigger>
            <TooltipPortal v-if="collapsed && !sidebarTransitioning && openTooltipKey === item.path">
              <TooltipContent class="app-tooltip" side="right" :side-offset="9">{{ item.label }}</TooltipContent>
            </TooltipPortal>
          </TooltipRoot>
        </nav>

        <TooltipRoot :open="openTooltipKey === '__collapse__'" @update:open="updateTooltip('__collapse__', $event)">
          <TooltipTrigger as-child>
            <button
              class="sidebar-collapse-button"
              type="button"
              :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
              :aria-expanded="!collapsed"
              @click="toggleSidebar"
            >
              <MorphIcon :icon="collapsed ? PanelLeftOpen : PanelLeftClose" :size="18" reduced-motion="user" aria-hidden="true" />
              <span>{{ collapsed ? '展开侧栏' : '收起侧栏' }}</span>
            </button>
          </TooltipTrigger>
          <TooltipPortal v-if="collapsed && !sidebarTransitioning && openTooltipKey === '__collapse__'">
            <TooltipContent class="app-tooltip" side="right" :side-offset="9">展开侧栏</TooltipContent>
          </TooltipPortal>
        </TooltipRoot>
      </aside>

      <div v-if="mobileNavOpen" class="sidebar-scrim" @click="mobileNavOpen = false"></div>

      <main class="main-area">
        <div v-if="insecure" class="security-banner">当前是局域网 HTTP 模式。对公网开放前必须接入 HTTPS。</div>
        <header class="topbar">
          <div class="topbar-left">
            <button class="mobile-menu" type="button" aria-label="打开导航" @click="mobileNavOpen = true">☰</button>
            <div class="customer-switcher">
              <span>当前客户</span>
              <SearchCombobox
                :model-value="session.selectedCustomerScopeValue"
                :options="customerOptions"
                :disabled="session.customers.length === 0"
                :placeholder="session.customers.length ? '选择客户' : '暂无可用客户'"
                search-placeholder="搜索客户…"
                appearance="toolbar"
                @update:model-value="session.selectCustomer"
              />
            </div>
          </div>
          <div class="profile-menu">
            <div class="avatar">{{ session.user?.displayName.slice(0, 1) }}</div>
            <div class="profile-copy">
              <strong>{{ session.user?.displayName }}</strong>
              <span>{{ session.isAdmin ? '系统管理员' : '业务操作员' }}</span>
            </div>
            <button class="text-button" type="button" @click="signOut">退出</button>
          </div>
        </header>
        <div class="page-frame">
          <RouterView v-slot="{ Component, route: currentRoute }">
            <Transition name="page" mode="out-in">
              <component :is="Component" :key="currentRoute.path" />
            </Transition>
          </RouterView>
        </div>
      </main>
    </div>
  </TooltipProvider>
</template>
