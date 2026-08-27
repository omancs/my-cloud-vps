<template>
  <div>
    <!-- Toolbar -->
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap">
        <n-input v-model:value="search" placeholder="搜索节点名/地址" clearable style="width:200px" @update:value="loadNodes" />
        <n-select v-model:value="filterProtocol" :options="protocolOptions" placeholder="协议" clearable style="width:120px" @update:value="loadNodes" />
        <n-select v-model:value="filterStatus" :options="statusOptions" placeholder="状态" clearable style="width:120px" @update:value="loadNodes" />
        <n-button @click="loadNodes">🔍 搜索</n-button>
        <n-button type="primary" @click="showAdd = true">➕ 手动添加</n-button>
        <n-button
          v-if="checkedIds.length"
          type="error"
          @click="handleBatchDelete"
        >
          🗑 删除选中 ({{ checkedIds.length }})
        </n-button>
        <n-text depth="3" style="margin-left:auto; font-size:13px">共 {{ total }} 个节点</n-text>
      </div>
    </n-card>

    <n-card :bordered="false" style="border-radius:12px">
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
      />
    </n-card>

    <!-- Add Node Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="手动添加节点" style="width:520px; border-radius:12px">
      <n-tabs v-model:value="addTab">
        <n-tab-pane name="uri" tab="URI 格式">
          <n-form-item label="节点 URI">
            <n-input v-model:value="uriInput" type="textarea" :rows="4" placeholder="vmess://... 或 vless://... 或 ss://..." />
          </n-form-item>
          <n-button type="primary" block @click="handleAddByUri">解析并添加</n-button>
        </n-tab-pane>
        <n-tab-pane name="manual" tab="手动填写">
          <n-form :model="nodeForm" label-placement="left" label-width="80px">
            <n-form-item label="名称"><n-input v-model:value="nodeForm.name" /></n-form-item>
            <n-form-item label="协议">
              <n-select v-model:value="nodeForm.protocol" :options="protocolOptions.filter(p => p.value)" />
            </n-form-item>
            <n-form-item label="地址"><n-input v-model:value="nodeForm.address" /></n-form-item>
            <n-form-item label="端口"><n-input-number v-model:value="nodeForm.port" :min="1" :max="65535" style="width:100%" /></n-form-item>
          </n-form>
          <n-button type="primary" block @click="handleAddManual">添加节点</n-button>
        </n-tab-pane>
      </n-tabs>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, h, reactive, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NModal, NForm, NFormItem,
  NInput, NInputNumber, NSelect, NSpace, NTag, NPopconfirm, NTabs,
  NTabPane, useMessage,
} from 'naive-ui'
import { nodeApi } from '../api'

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
const showAdd = ref(false)
const addTab = ref('uri')
const uriInput = ref('')
const nodeForm = reactive({ name: '', protocol: 'vmess', address: '', port: 443 })
const saving = ref(false)

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
  { label: '全部', value: null },
  { label: '正常', value: 'ok' },
  { label: '超时', value: 'timeout' },
  { label: '未测试', value: 'unknown' },
]

function latencyTag(ms) {
  if (ms === null || ms === undefined) return h(NTag, { size: 'small' }, { default: () => '—' })
  const color = ms < 150 ? 'success' : ms < 400 ? 'warning' : 'error'
  return h(NTag, { type: color, size: 'small' }, { default: () => `${Math.round(ms)}ms` })
}

function purityTag(status) {
  const map = { clean: ['success', '✅ 纯净'], partial: ['warning', '⚠️ 部分'], dirty: ['error', '❌ 污染'], unknown: ['default', '未检测'] }
  const [type, label] = map[status] || ['default', '未知']
  return h(NTag, { type, size: 'small' }, { default: () => label })
}

const columns = [
  { type: 'selection' },
  { title: '名称', key: 'name', ellipsis: { tooltip: true }, width: 180 },
  {
    title: '协议',
    key: 'protocol',
    width: 80,
    render: (row) => h(NTag, { size: 'small', type: 'info' }, { default: () => row.protocol.toUpperCase() }),
  },
  { title: '地址', key: 'address', ellipsis: { tooltip: true }, width: 180 },
  { title: '端口', key: 'port', width: 70 },
  {
    title: 'TCP延迟',
    key: 'latency_ms',
    width: 90,
    render: (row) => latencyTag(row.latency_ms),
  },
  {
    title: '代理延迟',
    key: 'real_latency_ms',
    width: 90,
    render: (row) => latencyTag(row.real_latency_ms),
  },
  { title: '国家', key: 'ip_country', width: 70 },
  {
    title: '纯净度',
    key: 'purity_status',
    width: 100,
    render: (row) => purityTag(row.purity_status),
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) => h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
      trigger: () => h(NButton, { size: 'small', type: 'error' }, { default: () => '删除' }),
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

async function handleAddByUri() {
  const uri = uriInput.value.trim()
  if (!uri) { message.warning('请输入节点 URI'); return }
  saving.value = true
  try {
    // Simple client-side parse for display; server does the real parse via subscription refresh
    // For manual single node, post raw_config and let backend handle
    await nodeApi.create({
      name: uri.substring(0, 30),
      protocol: uri.split('://')[0],
      address: 'pending',
      port: 0,
      raw_config: uri,
    })
    message.success('节点已添加')
    showAdd.value = false
    uriInput.value = ''
    loadNodes()
  } catch (e) {
    message.error(e.response?.data?.detail || '添加失败')
  } finally {
    saving.value = false
  }
}

async function handleAddManual() {
  if (!nodeForm.name || !nodeForm.address) { message.warning('请填写名称和地址'); return }
  try {
    await nodeApi.create({ ...nodeForm })
    message.success('节点已添加')
    showAdd.value = false
    loadNodes()
  } catch (e) {
    message.error('添加失败')
  }
}

onMounted(loadNodes)
</script>
