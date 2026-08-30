<template>
  <div>
    <!-- Testing controls -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center">
        <n-text strong style="font-size: 14px">一键测试：</n-text>
        <n-button type="primary" :loading="running.tcp" @click="run('tcp')">
          ⚡ TCP 物理延迟
        </n-button>
        <n-button type="info" :loading="running.proxy" @click="run('proxy')">
          🚀 真实代理测速
        </n-button>
        <n-button type="warning" :loading="running.purity" @click="run('purity')">
          🔍 IP纯净度与流媒体解锁
        </n-button>
        <n-button type="success" :loading="running.full" @click="run('full')">
          🔄 全量流水线测试
        </n-button>
      </div>

      <n-alert v-if="lastMsg" type="info" style="margin-top: 12px; border-radius: 8px" :show-icon="false">
        {{ lastMsg }}
      </n-alert>
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
import { ref, reactive, h, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NAlert, NTag, useMessage,
} from 'naive-ui'
import { testApi } from '../api'

const message = useMessage()
const results = ref([])
const loading = ref(false)
const lastMsg = ref('')

const running = reactive({ tcp: false, proxy: false, purity: false, full: false })

function typeTag(type) {
  const map = {
    tcp_ping: ['primary', 'TCP Ping'],
    proxy_speed: ['info', '代理测速'],
    purity: ['warning', '纯净度/解锁'],
  }
  const [t, label] = map[type] || ['default', type]
  return h(NTag, { type: t, size: 'tiny' }, { default: () => label })
}

const columns = [
  { title: '节点ID', key: 'node_id', width: 70 },
  {
    title: '测试类型',
    key: 'test_type',
    width: 100,
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
    render: (row) => row.tested_at ? new Date(row.tested_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—',
  },
]

async function run(type) {
  const key = type === 'tcp' ? 'tcp' : type === 'proxy' ? 'proxy' : type === 'purity' ? 'purity' : 'full'
  running[key] = true
  try {
    let res
    if (type === 'tcp') res = await testApi.tcpPing({})
    else if (type === 'proxy') res = await testApi.proxySpeed({})
    else if (type === 'purity') res = await testApi.purity({})
    else res = await testApi.full({})

    lastMsg.value = res.data.message
    message.success(res.data.message)
    setTimeout(loadResults, 4000)
  } catch (e) {
    message.error('启动测试失败')
  } finally {
    running[key] = false
  }
}

async function loadResults() {
  loading.value = true
  try {
    const res = await testApi.results({ limit: 100 })
    results.value = res.data
  } catch (e) {
    message.error('加载测试记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadResults)
</script>
