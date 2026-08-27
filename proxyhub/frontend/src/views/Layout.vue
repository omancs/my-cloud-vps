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

        <!-- Traffic pill -->
        <div v-if="traffic" style="display:flex; align-items:center; gap:12px">
          <n-tooltip trigger="hover">
            <template #trigger>
              <div class="traffic-pill" :class="traffic.alert">
                <span>📶</span>
                <span>{{ traffic.used_gb }} GB / {{ traffic.quota_gb }} GB</span>
                <n-progress
                  type="line"
                  :percentage="traffic.usage_pct"
                  :color="trafficColor"
                  :rail-color="'rgba(0,0,0,0.08)'"
                  :show-indicator="false"
                  style="width:80px"
                />
              </div>
            </template>
            当月出站流量：{{ traffic.used_gb }} GB / {{ traffic.quota_gb }} GB（{{ traffic.usage_pct }}%）
          </n-tooltip>

          <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
            <n-button text style="font-size:14px">
              👤 {{ auth.username }} ▾
            </n-button>
          </n-dropdown>
        </div>
        <div v-else>
          <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
            <n-button text style="font-size:14px">👤 {{ auth.username }} ▾</n-button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <!-- Exceeded alert banner -->
      <n-alert
        v-if="traffic && traffic.alert === 'exceeded'"
        type="error"
        style="border-radius:0; position:sticky; top:56px; z-index:98"
      >
        ⚠️ 当月出站流量已超出免费额度（{{ traffic.used_gb }} GB / {{ traffic.quota_gb }} GB），请注意控制使用！
      </n-alert>
      <n-alert
        v-else-if="traffic && traffic.alert === 'warning'"
        type="warning"
        style="border-radius:0; position:sticky; top:56px; z-index:98"
      >
        ⚠️ 当月出站流量已达 {{ traffic.usage_pct }}%，接近免费额度上限！
      </n-alert>

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
import { ref, computed, h, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NLayout, NLayoutSider, NLayoutHeader, NLayoutContent,
  NMenu, NBreadcrumb, NBreadcrumbItem, NButton, NDropdown,
  NProgress, NTooltip, NAlert, useMessage,
} from 'naive-ui'
import { useAuthStore } from '../store/auth'
import { trafficApi } from '../api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const collapsed = ref(false)
const traffic = ref(null)
let trafficTimer = null

const menuOptions = [
  { label: '总览', key: '/dashboard', icon: () => h('span', '📊') },
  { label: '订阅管理', key: '/subscriptions', icon: () => h('span', '📋') },
  { label: '节点管理', key: '/nodes', icon: () => h('span', '🌐') },
  { label: '网络分组', key: '/networks', icon: () => h('span', '📡') },
  { label: '测速检测', key: '/testing', icon: () => h('span', '⚡') },
  { label: '分流规则', key: '/rules', icon: () => h('span', '🔀') },
]

const activeKey = computed(() => route.path)

const pageNames = {
  '/dashboard': '总览',
  '/subscriptions': '订阅管理',
  '/nodes': '节点管理',
  '/networks': '网络分组',
  '/testing': '测速检测',
  '/rules': '分流规则',
}
const currentPageName = computed(() => pageNames[route.path] || 'ProxyHub')

const trafficColor = computed(() => {
  if (!traffic.value) return '#6366f1'
  const pct = traffic.value.usage_pct
  if (pct >= 100) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
})

function handleNav(key) { router.push(key) }

const userMenuOptions = [{ label: '退出登录', key: 'logout' }]

function handleUserMenu(key) {
  if (key === 'logout') {
    auth.logout()
    message.success('已退出')
    router.push('/login')
  }
}

async function loadTraffic() {
  try {
    const res = await trafficApi.usage()
    traffic.value = res.data
  } catch (e) { /* silently ignore */ }
}

onMounted(() => {
  loadTraffic()
  // Refresh traffic every 5 minutes
  trafficTimer = setInterval(loadTraffic, 5 * 60 * 1000)
})
onUnmounted(() => { if (trafficTimer) clearInterval(trafficTimer) })
</script>

<style scoped>
.sider-logo {
  height: 56px; display: flex; align-items: center;
  padding: 0 18px; gap: 10px; border-bottom: 1px solid #efeff5; overflow: hidden;
}
.logo-icon { font-size: 24px; flex-shrink: 0; }
.logo-text { font-size: 18px; font-weight: 700; color: #6366f1; white-space: nowrap; }

.traffic-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 20px; background: #f5f5f5;
  font-size: 12px; font-weight: 500; cursor: default;
}
.traffic-pill.warning { background: #fff3cd; color: #856404; }
.traffic-pill.exceeded { background: #f8d7da; color: #842029; }
</style>
