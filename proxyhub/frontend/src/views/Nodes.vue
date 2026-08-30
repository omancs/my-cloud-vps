<template>
  <div>
    <!-- Action bar -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="showSmartImport = true">⚡ 智能导入 (NekoBox)</n-button>
        <n-input v-model:value="search" placeholder="搜索名称/IP" clearable style="width: 150px" @update:value="loadNodes" />
        <n-select v-model:value="filterProtocol" :options="protocolOptions" placeholder="协议" clearable style="width: 105px" @update:value="loadNodes" />
        <n-select v-model:value="filterStatus" :options="statusOptions" placeholder="状态" clearable style="width: 105px" @update:value="loadNodes" />
        <n-button @click="loadNodes">🔍 筛选</n-button>
        <n-button v-if="checkedIds.length" type="error" @click="handleBatchDelete">
          🗑 删除选中 ({{ checkedIds.length }})
        </n-button>
        <n-text depth="3" style="font-size: 13px; margin-left: auto">
          共 {{ total }} 个节点
        </n-text>
      </div>
    </n-card>

    <!-- Nodes Table -->
    <n-card :bordered="false" style="border-radius: 12px">
      <n-data-table
        :columns="columns"
        :data="nodes"
        :loading="loading"
        :pagination="pagination"
        :row-key="(row) => row.id"
        v-model:checked-row-keys="checkedIds"
        @update:page="handlePageChange"
        remote
        striped
        size="small"
        :scroll-x="900"
      />
    </n-card>

    <!-- Smart Import Modal -->
    <SmartImportModal v-model:show="showSmartImport" @imported="loadNodes" />
  </div>
</template>

<script setup>
import { ref, h, reactive, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NInput, NSelect, NTag,
  NPopconfirm, NSpace, useMessage,
} from 'naive-ui'
import { nodeApi } from '../api'
import SmartImportModal from '../components/SmartImportModal.vue'

const message = useMessage()
const nodes = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 50
const search = ref('')
const filterProtocol = ref(null)
const filterStatus = ref(null)
const checkedIds = ref([])
const showSmartImport = ref(false)

const pagination = reactive({ page: 1, pageSize, pageCount: 1, itemCount: 0 })

const protocolOptions = [
  { label: '全部', value: null },
  { label: 'VMess', value: 'vmess' },
  { label: 'VLESS', value: 'vless' },
  { label: 'Shadowsocks', value: 'ss' },
  { label: 'Trojan', value: 'trojan' },
  { label: 'Hysteria2', value: 'hy2' },
]

const statusOptions = [
  { label: '全部状态', value: null },
  { label: '正常可用', value: 'ok' },
  { label: '超时/失效', value: 'timeout' },
]

function latencyTag(ms) {
  if (ms === null || ms === undefined) return h('span', { style: 'color:#aaa' }, '—')
  const color = ms < 150 ? 'success' : ms < 400 ? 'warning' : 'error'
  return h(NTag, { type: color, size: 'tiny' }, { default: () => `${Math.round(ms)}ms` })
}

function purityTag(row) {
  const status = row.purity_status
  const isRes = row.is_residential
  if (status === 'clean') return h(NTag, { type: 'success', size: 'tiny' }, { default: () => '✅ 纯净住宅' })
  if (status === 'partial') return h(NTag, { type: 'warning', size: 'tiny' }, { default: () => isRes ? '住宅' : '良好' })
  if (status === 'dirty') return h(NTag, { type: 'error', size: 'tiny' }, { default: () => '机房' })
  return h('span', { style: 'color:#bbb; font-size:12px' }, '未检测')
}

const columns = [
  { type: 'selection' },
  { title: '节点名称', key: 'name', ellipsis: { tooltip: true }, width: 170 },
  {
    title: '协议',
    key: 'protocol',
    width: 80,
    render: (row) => h(NTag, { size: 'tiny', type: 'info' }, { default: () => (row.protocol || '').toUpperCase() }),
  },
  { title: '国家', key: 'ip_country', width: 65, render: (row) => row.ip_country ? h(NTag, { size: 'tiny', bordered: false }, { default: () => row.ip_country }) : '—' },
  { title: '地址', key: 'address', ellipsis: { tooltip: true }, width: 140 },
  {
    title: '物理延迟',
    key: 'latency_ms',
    width: 85,
    render: (row) => latencyTag(row.latency_ms),
  },
  {
    title: '代理延迟',
    key: 'real_latency_ms',
    width: 85,
    render: (row) => latencyTag(row.real_latency_ms),
  },
  {
    title: '纯净度',
    key: 'purity_status',
    width: 90,
    render: (row) => purityTag(row),
  },
  {
    title: '解锁',
    key: 'unlocks',
    width: 110,
    render: (row) => {
      const tags = []
      if (row.netflix_unlock) tags.push(h(NTag, { size: 'tiny', type: 'error', style: 'margin-right:2px' }, { default: () => 'NF' }))
      if (row.openai_unlock) tags.push(h(NTag, { size: 'tiny', type: 'success', style: 'margin-right:2px' }, { default: () => 'AI' }))
      if (row.youtube_unlock) tags.push(h(NTag, { size: 'tiny', type: 'warning' }, { default: () => 'YT' }))
      return tags.length ? h('div', { style: 'display:flex; flex-wrap:nowrap' }, tags) : h('span', { style: 'color:#bbb; font-size:12px' }, '—')
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 65,
    render: (row) => h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
      trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
      default: () => '确认删除此节点？',
    }),
  },
]

async function loadNodes() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize,
      search: search.value || undefined,
      protocol: filterProtocol.value || undefined,
      status: filterStatus.value || undefined,
    }
    const res = await nodeApi.list(params)
    nodes.value = res.data.items
    total.value = res.data.total
    pagination.itemCount = res.data.total
    pagination.pageCount = Math.ceil(res.data.total / pageSize)
  } catch (e) {
    message.error('加载节点失败')
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  page.value = p
  pagination.page = p
  loadNodes()
}

async function handleDelete(row) {
  try {
    await nodeApi.remove(row.id)
    message.success('已删除')
    loadNodes()
  } catch (e) {
    message.error('删除失败')
  }
}

async function handleBatchDelete() {
  try {
    await nodeApi.batchDelete(checkedIds.value)
    message.success(`已删除 ${checkedIds.value.length} 个节点`)
    checkedIds.value = []
    loadNodes()
  } catch (e) {
    message.error('批量删除失败')
  }
}

onMounted(loadNodes)
</script>
