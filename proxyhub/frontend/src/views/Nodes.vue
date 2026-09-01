<template>
  <div>
    <!-- Action bar -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="showSmartImport = true">⚡ 智能导入 (NekoBox)</n-button>
        <n-button secondary @click="handleBatchRename">✨ 一键去广告重命名</n-button>
        <n-button secondary @click="handleBatchTag">🏷️ 生成智能标签</n-button>
        <n-button quaternary @click="handleUnquarantine">🚑 移出隔离区</n-button>

        <n-input v-model:value="search" placeholder="搜索名称/IP" clearable style="width: 130px" @update:value="loadNodes" />
        <n-select v-model:value="filterProtocol" :options="protocolOptions" placeholder="协议" clearable style="width: 100px" @update:value="loadNodes" />
        <n-select v-model:value="filterStatus" :options="statusOptions" placeholder="状态" clearable style="width: 100px" @update:value="loadNodes" />

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
        :scroll-x="1000"
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
  { label: '全部协议', value: null },
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

const columns = [
  { type: 'selection' },
  {
    title: '节点名称',
    key: 'name',
    width: 220,
    render: (row) => {
      const items = [
        h('div', { style: 'font-weight: 500; display:flex; align-items:center; gap:6px;' }, [
          row.is_quarantined ? h(NTag, { type: 'error', size: 'tiny' }, { default: () => '🚨 隔离中' }) : null,
          h('span', row.name),
        ])
      ]
      if (Array.isArray(row.tags) && row.tags.length > 0) {
        items.push(h('div', { style: 'display:flex; gap:4px; margin-top:4px; flex-wrap:wrap;' },
          row.tags.slice(0, 3).map(t => h(NTag, { size: 'tiny', bordered: false, type: 'info' }, { default: () => t }))
        ))
      }
      return h('div', items)
    }
  },
  {
    title: '协议',
    key: 'protocol',
    width: 85,
    render: (row) => h(NTag, { size: 'tiny' }, { default: () => row.protocol.toUpperCase() }),
  },
  {
    title: '服务器地址',
    key: 'address',
    width: 140,
    render: (row) => `${row.address}:${row.port}`,
    ellipsis: { tooltip: true },
  },
  {
    title: '延迟',
    key: 'latency_ms',
    width: 80,
    render: (row) => latencyTag(row.real_latency_ms || row.latency_ms),
  },
  {
    title: '测速',
    key: 'download_speed',
    width: 85,
    render: (row) => row.download_speed != null
      ? h(NTag, { type: row.download_speed > 10 ? 'success' : 'default', size: 'tiny' }, { default: () => `${row.download_speed} M` })
      : h('span', { style: 'color:#bbb' }, '—'),
  },
  {
    title: '流媒体/AI解锁',
    key: 'unlocks',
    width: 130,
    render: (row) => h(NSpace, { size: 'tiny' }, {
      default: () => [
        row.openai_unlock ? h(NTag, { type: 'success', size: 'tiny' }, { default: () => 'AI' }) : null,
        row.netflix_unlock ? h(NTag, { type: 'error', size: 'tiny' }, { default: () => 'NF' }) : null,
        row.youtube_unlock ? h(NTag, { type: 'warning', size: 'tiny' }, { default: () => 'YT' }) : null,
        row.is_residential ? h(NTag, { type: 'info', size: 'tiny' }, { default: () => '住宅' }) : null,
      ].filter(Boolean),
    }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 75,
    render: (row) => h(NPopconfirm, { onPositiveClick: () => handleDelete(row.id) }, {
      trigger: () => h(NButton, { size: 'tiny', type: 'error', quaternary: true }, { default: () => '删除' }),
      default: () => '确认删除该节点？',
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
    pagination.page = page.value
    pagination.pageCount = Math.ceil(res.data.total / pageSize)
  } catch (e) {
    message.error('加载节点失败')
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  page.value = p
  loadNodes()
}

async function handleBatchRename() {
  try {
    const ids = checkedIds.value.length ? checkedIds.value : null
    const res = await nodeApi.batchRename(ids)
    message.success(res.data.message)
    loadNodes()
  } catch (e) {
    message.error('重命名失败')
  }
}

async function handleBatchTag() {
  try {
    const ids = checkedIds.value.length ? checkedIds.value : null
    const res = await nodeApi.batchTag(ids)
    message.success(res.data.message)
    loadNodes()
  } catch (e) {
    message.error('生成标签失败')
  }
}

async function handleUnquarantine() {
  try {
    const ids = checkedIds.value.length ? checkedIds.value : null
    const res = await nodeApi.batchUnquarantine(ids)
    message.success(res.data.message)
    loadNodes()
  } catch (e) {
    message.error('移出隔离区失败')
  }
}

async function handleDelete(id) {
  try {
    await nodeApi.remove(id)
    message.success('节点已删除')
    loadNodes()
  } catch (e) {
    message.error('删除失败')
  }
}

async function handleBatchDelete() {
  if (!checkedIds.value.length) return
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
