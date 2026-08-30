<template>
  <n-layout style="min-height: 100vh" :has-sider="!isMobile">
    <!-- Desktop Sidebar -->
    <n-layout-sider
      v-if="!isMobile"
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

    <!-- Mobile Drawer Sidebar -->
    <n-drawer v-model:show="showMobileDrawer" placement="left" :width="240">
      <div class="sider-logo">
        <span class="logo-icon">🔗</span>
        <span class="logo-text">ProxyHub</span>
      </div>
      <n-menu
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleMobileNav"
      />
    </n-drawer>

    <!-- Main Container -->
    <n-layout :style="{ marginLeft: isMobile ? '0' : (collapsed ? '64px' : '220px'), transition: 'margin 0.3s' }">
      <!-- Header -->
      <n-layout-header bordered class="layout-header">
        <div style="display: flex; align-items: center; gap: 10px">
          <!-- Mobile Hamburger -->
          <n-button v-if="isMobile" quaternary circle @click="showMobileDrawer = true">
            <template #icon><span>☰</span></template>
          </n-button>
          <span class="page-title">{{ currentPageName }}</span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px">
          <!-- Traffic Capsule -->
          <n-popover v-if="traffic" trigger="hover" placement="bottom">
            <template #trigger>
              <div class="traffic-pill" :class="traffic.alert">
                <span>📶</span>
                <span v-if="!isMobile">{{ traffic.used_gb }} GB / {{ traffic.quota_gb }} GB</span>
                <span v-else style="font-size: 11px">{{ traffic.usage_pct }}%</span>
                <n-progress
                  type="line"
                  :percentage="traffic.usage_pct"
                  :color="trafficColor"
                  :rail-color="'rgba(0,0,0,0.08)'"
                  :show-indicator="false"
                  :style="{ width: isMobile ? '36px' : '60px' }"
                />
              </div>
            </template>
            <div style="font-size: 13px; line-height: 1.6">
              <div><b>GCP VPS 当月出站流量</b></div>
              <div>已用: <b>{{ traffic.used_gb }} GB</b> / 额度: {{ traffic.quota_gb }} GB</div>
              <div>使用占比: <b>{{ traffic.usage_pct }}%</b></div>
              <div>监控网卡: {{ traffic.interface }}</div>
            </div>
          </n-popover>

          <!-- Dark/Light Theme Toggle -->
          <n-button quaternary circle @click="themeStore.toggleTheme">
            <template #icon>
              <span>{{ themeStore.isDark ? '🌙' : '☀️' }}</span>
            </template>
          </n-button>

          <!-- User dropdown -->
          <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
            <n-button quaternary size="small">
              👤 <span v-if="!isMobile" style="margin-left: 4px">{{ auth.username }}</span>
            </n-button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <!-- Traffic Warning Banners -->
      <n-alert
        v-if="traffic && traffic.alert === 'exceeded'"
        type="error"
        style="border-radius:0; position:sticky; top:56px; z-index:98"
      >
        ⚠️ 当月出站流量已超出限额（{{ traffic.used_gb }} GB / {{ traffic.quota_gb }} GB），请注意控制使用！
      </n-alert>
      <n-alert
        v-else-if="traffic && traffic.alert === 'warning'"
        type="warning"
        style="border-radius:0; position:sticky; top:56px; z-index:98"
      >
        ⚠️ 当月出站流量已达 {{ traffic.usage_pct }}%，接近免费额度！
      </n-alert>

      <!-- Page Content -->
      <n-layout-content :class="['layout-content', { 'mobile-content': isMobile }]">
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
import { ref, computed, h, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NLayout, NLayoutSider, NLayoutHeader, NLayoutContent,
  NMenu, NButton, NDropdown, NProgress, NPopover, NAlert,
  NDrawer, useMessage,
} from 'naive-ui'
import { useAuthStore } from '../store/auth'
import { useThemeStore } from '../store/theme'
import { trafficApi } from '../api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()

const collapsed = ref(false)
const showMobileDrawer = ref(false)
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value < 768)

const traffic = ref(null)
let trafficTimer = null

function handleResize() {
  windowWidth.value = window.innerWidth
}

const menuOptions = [
  { label: '总览面板', key: '/dashboard', icon: () => h('span', '📊') },
  { label: '订阅管理', key: '/subscriptions', icon: () => h('span', '📋') },
  { label: '节点管理', key: '/nodes', icon: () => h('span', '🌐') },
  { label: '聚合分组', key: '/networks', icon: () => h('span', '📡') },
  { label: '测速检测', key: '/testing', icon: () => h('span', '⚡') },
  { label: '分流规则', key: '/rules', icon: () => h('span', '🔀') },
]

const activeKey = computed(() => route.path)

const pageNames = {
  '/dashboard': '总览面板',
  '/subscriptions': '订阅管理',
  '/nodes': '节点管理',
  '/networks': '聚合网络分组',
  '/testing': '节点测速与纯净度',
  '/rules': '自定义分流规则',
}
const currentPageName = computed(() => pageNames[route.path] || 'ProxyHub')

const trafficColor = computed(() => {
  if (!traffic.value) return '#6366f1'
  const pct = traffic.value.usage_pct
  if (pct >= 100) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
})

function handleNav(key) {
  router.push(key)
}

function handleMobileNav(key) {
  showMobileDrawer.value = false
  router.push(key)
}

const userMenuOptions = [{ label: '退出登录', key: 'logout' }]

function handleUserMenu(key) {
  if (key === 'logout') {
    auth.logout()
    message.success('已退出登录')
    router.push('/login')
  }
}

async function loadTraffic() {
  try {
    const res = await trafficApi.usage()
    traffic.value = res.data
  } catch (e) {}
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadTraffic()
  trafficTimer = setInterval(loadTraffic, 3 * 60 * 1000)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (trafficTimer) clearInterval(trafficTimer)
})
</script>

<style scoped>
.layout-header {
  padding: 0 16px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 99;
  backdrop-filter: blur(8px);
}

.sider-logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 18px;
  gap: 10px;
  border-bottom: 1px solid rgba(150, 150, 150, 0.15);
  overflow: hidden;
}
.logo-icon { font-size: 24px; flex-shrink: 0; }
.logo-text { font-size: 18px; font-weight: 700; color: #6366f1; white-space: nowrap; }

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.traffic-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 20px;
  background: rgba(150, 150, 150, 0.1);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.traffic-pill.warning { background: #fff3cd; color: #856404; }
.traffic-pill.exceeded { background: #f8d7da; color: #842029; }

.layout-content {
  padding: 20px;
  min-height: calc(100vh - 56px);
}
.mobile-content {
  padding: 12px;
}
</style>
