<template>
  <div>
    <!-- Testing controls -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center">
        <n-text strong style="font-size: 14px">一键测试：</n-text>
        <n-button type="primary" :loading="running.latency" @click="run('latency')">
          ⚡ 快速延迟 (UnifiedDelay)
        </n-button>
        <n-button type="info" :loading="running.bandwidth" @click="run('bandwidth')">
          🚀 带宽测速 (MB/s)
        </n-button>
        <n-button type="warning" :loading="running.purity" @click="run('purity')">
          🔍 纯净度 & 流媒体/AI
        </n-button>
        <n-button type="success" :loading="running.full" @click="run('full')">
          🔄 全量三阶段流水线
        </n-button>
      </div>

      <!-- Real-time Progress Board -->
      <div v-if="progress.is_running || progress.total > 0" style="margin-top: 16px; background: rgba(0,0,0,0.03); padding: 14px; border-radius: 8px">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px">
          <n-text strong style="font-size: 13px">{{ progress.message }}</n-text>
          <n-text depth="3" style="font-size: 12px">
            平均延迟：<span style="font-weight: 600; color: #18a058">{{ progress.avg_latency }} ms</span>
          </n-text>
        </div>
        <n-progress
          type="line"
          :percentage="calcPercentage"
          :status="progress.is_running ? 'info' : 'success'"
          :indicator-placement="'inside'"
          processing
        />
        <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 12px">
          <span>🟢 存活: <b>{{ progress.alive }}</b></span>
          <span>🔴 失败: <b>{{ progress.failed }}</b></span>
          <span>📦 总计: <b>{{ progress.total }}</b></span>
        </div>
      </div>
    </n-card>

    <!-- Test History Card -->
    <n-card title="测试历史记录" :bordered="false" style="border-radius: 12px">
      <template #header-extra>
        <n-button size="small" quaternary @click="loadResults">🔄 刷新记录</n-button>
      </template>
      <n-data-table
        :columns="columns"
        :data="results"
        :loading="loading"
        :pagination="{ pageSize: 25 }"
        size="small"
        striped
        :scroll-x="600"
      />
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, h, onMounted, onUnmounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NProgress, NTag, useMessage,
} from 'naive-ui'
import { testApi } from '../api'

const message = useMessage()
const results = ref([])
const loading = ref(false)
let timer = null

const running = reactive({ latency: false, bandwidth: false, purity: false, full: false })

const progress = ref({
  is_running: false,
  task_type: '',
  total: 0,
  completed: 0,
  alive: 0,
  failed: 0,
  avg_latency: 0.0,
  message: '空闲',
})

const calcPercentage = computed(() => {
  if (!progress.value.total) return 0
  return Math.min(100, Math.round((progress.value.completed / progress.value.total) * 100))
})

async function pollProgress() {
  try {
    const res = await testApi.getProgress()
    progress.value = res.data
    if (res.data.is_running) {
      if (!timer) {
        timer = setInterval(pollProgress, 800)
      }
    } else {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
      running.latency = false
      running.bandwidth = false
      running.purity = false
      running.full = false
      loadResults()
    }
  } catch (e) {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }
}

async function run(type) {
  running[type] = true
  try {
    if (type === 'latency') await testApi.latency({})
    else if (type === 'bandwidth') await testApi.bandwidth({})
    else if (type === 'purity') await testApi.purity({})
    else if (type === 'full') await testApi.full({})
    message.success('测试任务已启动，正在后台高并发测速...')
    pollProgress()
    if (!timer) {
      timer = setInterval(pollProgress, 800)
    }
  } catch (e) {
    running[type] = false
    message.error('启动测试失败')
  }
}

function typeTag(type) {
  const map = {
    latency: ['primary', 'UnifiedDelay'],
    tcp_ping: ['primary', 'TCP Ping'],
    bandwidth: ['info', '带宽测速'],
    proxy_speed: ['info', '代理测速'],
    purity: ['warning', '纯净度/解锁'],
  }
  const [t, label] = map[type] || ['default', type]
  return h(NTag, { type: t, size: 'tiny' }, { default: () => label })
}

const columns = [
  { title: '节点ID', key: 'node_id', width: 75 },
  {
    title: '测试类型',
    key: 'test_type',
    width: 120,
    render: (row) => typeTag(row.test_type),
  },
  {
    title: '状态',
    key: 'success',
    width: 75,
    render: (row) => h(NTag, { type: row.success ? 'success' : 'error', size: 'tiny' }, { default: () => row.success ? '成功' : '失败' }),
  },
  {
    title: '延迟 / 详情',
    key: 'latency_ms',
    render: (row) => {
      if (row.latency_ms != null) {
        const speed = row.download_mbps ? ` · ${row.download_mbps} Mbps` : ''
        return `${Math.round(row.latency_ms)} ms${speed}`
      }
      if (row.details) {
        const d = row.details
        if (d.ip_country) return `[${d.ip_country}] ${d.ip_address || ''} (${d.purity_status || ''})`
        if (d.error) return d.error
      }
      return '—'
    },
  },
  {
    title: '时间',
    key: 'tested_at',
    width: 140,
    render: (row) => row.tested_at ? new Date(row.tested_at).toLocaleTimeString('zh-CN') : '—',
  },
]

async function loadResults() {
  loading.value = true
  try {
    const res = await testApi.results({ limit: 50 })
    results.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    message.error('加载记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadResults()
  pollProgress()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
