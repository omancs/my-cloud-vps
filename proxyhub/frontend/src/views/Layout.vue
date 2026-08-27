<template>
  <n-layout style="min-height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
      style="position: fixed; height: 100vh; z-index: 100"
    >
      <div class="sider-logo">
        <span class="logo-icon">🔗</span>
        <span v-if="!collapsed" class="logo-text">ProxyHub</span>
      </div>
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleNav"
      />
    </n-layout-sider>

    <n-layout :style="{ marginLeft: collapsed ? '64px' : '220px', transition: 'margin 0.3s' }">
      <!-- Top bar -->
      <n-layout-header bordered style="padding: 0 24px; height: 56px; display: flex; align-items: center; justify-content: space-between; background:#fff; position:sticky; top:0; z-index:99">
        <n-breadcrumb>
          <n-breadcrumb-item>{{ currentPageName }}</n-breadcrumb-item>
        </n-breadcrumb>
        <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
          <n-button text style="font-size:14px">
            👤 {{ auth.username }}
            <n-icon style="margin-left:4px"><chevron-down /></n-icon>
          </n-button>
        </n-dropdown>
      </n-layout-header>

      <!-- Content -->
      <n-layout-content style="padding: 24px; min-height: calc(100vh - 56px)">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { ref, computed, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NLayout, NLayoutSider, NLayoutHeader, NLayoutContent,
  NMenu, NBreadcrumb, NBreadcrumbItem, NButton, NDropdown, NIcon,
  useMessage,
} from 'naive-ui'
import { useAuthStore } from '../store/auth'

// Icon components (inline SVG via render functions)
const HomeIcon = { render: () => h('span', '📊') }
const SubIcon = { render: () => h('span', '📋') }
const NodeIcon = { render: () => h('span', '🌐') }
const NetIcon = { render: () => h('span', '📡') }
const TestIcon = { render: () => h('span', '⚡') }
const ChevronDown = { render: () => h('span', '▾') }

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const collapsed = ref(false)

const menuOptions = [
  { label: '总览', key: '/dashboard', icon: () => h(HomeIcon) },
  { label: '订阅管理', key: '/subscriptions', icon: () => h(SubIcon) },
  { label: '节点管理', key: '/nodes', icon: () => h(NodeIcon) },
  { label: '网络分组', key: '/networks', icon: () => h(NetIcon) },
  { label: '测速检测', key: '/testing', icon: () => h(TestIcon) },
]

const activeKey = computed(() => route.path)

const pageNames = {
  '/dashboard': '总览',
  '/subscriptions': '订阅管理',
  '/nodes': '节点管理',
  '/networks': '网络分组',
  '/testing': '测速检测',
}
const currentPageName = computed(() => pageNames[route.path] || 'ProxyHub')

function handleNav(key) {
  router.push(key)
}

const userMenuOptions = [
  { label: '退出登录', key: 'logout' },
]

function handleUserMenu(key) {
  if (key === 'logout') {
    auth.logout()
    message.success('已退出')
    router.push('/login')
  }
}
</script>

<style scoped>
.sider-logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 18px;
  gap: 10px;
  border-bottom: 1px solid #efeff5;
  overflow: hidden;
}
.logo-icon { font-size: 24px; flex-shrink: 0; }
.logo-text { font-size: 18px; font-weight: 700; color: #6366f1; white-space: nowrap; }
</style>
