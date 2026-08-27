<template>
  <div>
    <!-- Quick Actions -->
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center">
        <n-text strong>快速测试（全部节点）：</n-text>
        <n-button type="primary" :loading="running.tcp" @click="run('tcp')">⚡ TCP Ping</n-button>
        <n-button type="info" :loading="running.proxy" @click="run('proxy')">🚀 代理测速</n-button>
        <n-button type="warning" :loading="running.purity" @click="run('purity')">🔍 纯净度检测</n-button>
        <n-button :loading="running.full" @click="run('full')" type="success">🔄 全量测试</n-button>
      </div>
      <n-alert v-if="lastMsg" type="info" style="margin-top:12px" :show-icon="false">
        {{ lastMsg }}
      </n-alert>
    </n-card>

    <!-- Results -->
    <n-card title="最近测试记录" :bordered="false" style="border-radius:12px">
      <template #header-extra>
        <n-button size="small" @click="loadResults">🔄 刷新</n-button>
      </template>
      <n-data-table
        :columns="columns"
        :data="results"
        :loading="loading"
        :pagination="{ pageSize: 30 }"
        size="small"
        striped
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
    tcp_ping: ['default', 'TCP Ping'],
    proxy_speed: ['info', '代理测速'],
    purity: ['warning', '纯净度'],
  }
  const [t, label] = map[type] || ['default', type]
  return h(NTag, { type: t, size: 'small' }, { default: () => label })
}

function successTag(ok) {
  return h(NTag, { type: ok ? 'success' : 'error', size: 'small' }, { default: () => ok ? '成功' : '失败' })
}

const columns = [
  { title: '节点ID', key: 'node_id', width: 80 },
  {
    title: '测试类型',
    key: 'test_type',
    width: 100,
    render: (row) => typeTag(row.test_type),
  },
  {
    title: '结果',
    key: 'success',
    width: 80,
    render: (row) => successTag(row.success),
  },
  {
    title: 'TCP延迟',
    key: 'latency_ms',
    width: 100,
    render: (row) => row.latency_ms != null ? `${Math.round(row.latency_ms)} ms` : '—',
  },
  {
    title: '下载速度',
    key: 'download_mbps',
    width: 110,
    render: (row) => row.download_mbps != null ? `${row.download_mbps} Mbps` : '—',
  },
  {
    title: '测试时间',
    key: 'tested_at',
    render: (row) => new Date(row.tested_at).toLocaleString('zh-CN'),
  },
]

async function run(type) {
  running[type === 'tcp' ? 'tcp' : type === 'proxy' ? 'proxy' : type === 'purity' ? 'purity' : 'full'] = true
  try {
    let res
    if (type === 'tcp') res = await testApi.tcpPing({})
    else if (type === 'proxy') res = await testApi.proxySpeed({})
    else if (type === 'purity') res = await testApi.purity({})
    else res = await testApi.full({})
    lastMsg.value = res.data.message
    message.success(res.data.message)
    // Auto refresh results after delay
    setTimeout(loadResults, 5000)
  } catch (e) {
    message.error('启动测试失败')
  } finally {
    running[type === 'tcp' ? 'tcp' : type === 'proxy' ? 'proxy' : type === 'purity' ? 'purity' : 'full'] = false
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
