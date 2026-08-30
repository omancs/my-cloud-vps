<template>
  <div>
    <!-- Top action bar -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="showAdd = true">➕ 创建聚合网络</n-button>
        <n-text depth="3" style="font-size: 13px; margin-left: auto">
          共 {{ networks.length }} 个聚合分组 · 支持安全 Token 与多国均衡优选
        </n-text>
      </div>
    </n-card>

    <!-- Network Cards Grid (Responsive) -->
    <n-grid :cols="1" :x-gap="16" :y-gap="16" responsive="screen" :item-responsive="true">
      <n-gi v-for="net in networks" :key="net.id" span="24 m:12">
        <n-card :bordered="false" style="border-radius: 12px; height: 100%">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px">
              <div>
                <span style="font-size: 16px; font-weight: 700">{{ net.name }}</span>
                <n-tag size="small" type="info" style="margin-left: 8px">{{ net.node_count }} 节点</n-tag>
                <n-tag v-if="net.auto_update" size="small" type="success" style="margin-left: 4px">每日自动优选</n-tag>
              </div>
              <n-space size="small">
                <n-button size="small" @click="openDetail(net)">管理节点</n-button>
                <n-popconfirm @positive-click="deleteNetwork(net)">
                  <template #trigger>
                    <n-button size="small" type="error" quaternary>删除</n-button>
                  </template>
                  确认删除此聚合网络分组？
                </n-popconfirm>
              </n-space>
            </div>
          </template>

          <n-text depth="3" style="font-size: 13px">{{ net.description || '暂无描述' }}</n-text>

          <n-divider style="margin: 12px 0" />

          <!-- Smart auto-select button -->
          <div style="margin-bottom: 12px">
            <n-button
              type="primary"
              secondary
              block
              :loading="optimizingId === net.id"
              @click="handleSmartSelect(net)"
            >
              ⚡ 一键智能优选 Top 50 (单国≤5节点)
            </n-button>
          </div>

          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px">
            <n-tag size="small" :bordered="false">排序：{{ net.sort_by === 'latency' ? 'TCP延迟' : '代理延迟' }}</n-tag>
            <n-tag size="small" :bordered="false">Token：{{ net.token ? net.token.substring(0, 8) + '...' : '无' }}</n-tag>
            <n-button size="tiny" quaternary @click="resetToken(net)">🔄 重置Token</n-button>
          </div>

          <!-- Export buttons -->
          <div style="display: flex; gap: 8px">
            <n-button size="small" block type="primary" ghost @click="copySubLink(net, 'clash')">
              📋 复制 Clash 订阅
            </n-button>
            <n-button size="small" block secondary @click="copySubLink(net, 'v2ray')">
              📋 复制 V2Ray 订阅
            </n-button>
          </div>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- Create Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="创建聚合网络" style="max-width: 440px; width: 95vw; border-radius: 12px">
      <n-form :model="form" label-placement="left" label-width="90px">
        <n-form-item label="名称"><n-input v-model:value="form.name" placeholder="例：家用宽带 / 手机流量" /></n-form-item>
        <n-form-item label="描述"><n-input v-model:value="form.description" placeholder="可选备注说明" /></n-form-item>
        <n-form-item label="排序方式">
          <n-select v-model:value="form.sort_by" :options="[{label:'按物理延迟',value:'latency'},{label:'按代理延迟',value:'real_latency'}]" />
        </n-form-item>
        <n-form-item label="每日自动优选">
          <n-switch v-model:value="form.auto_update" />
          <span style="margin-left: 8px; font-size: 12px; color: #888">每日凌晨自动填入最新 Top 50 节点</span>
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px">
          <n-button @click="showAdd = false">取消</n-button>
          <n-button type="primary" @click="handleAdd">确认创建</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Node management drawer -->
    <n-drawer v-model:show="showDetail" :width="drawerWidth" placement="right">
      <n-drawer-content :title="`${selectedNet?.name || ''} · 节点管理`" closable>
        <div style="margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap">
          <n-select
            v-model:value="selectedNodeIds"
            multiple
            filterable
            :options="allNodeOptions"
            placeholder="手动挑选节点加入分组"
            style="flex: 1; min-width: 200px"
          />
          <n-button type="primary" @click="handleAddNodes">添加</n-button>
          <n-button type="warning" secondary @click="handleSmartSelect(selectedNet)">⚡ 智能优选</n-button>
        </div>
        <n-data-table
          :columns="detailColumns"
          :data="netNodes"
          :loading="detailLoading"
          size="small"
          striped
          :scroll-x="480"
        />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { ref, h, reactive, computed, onMounted } from 'vue'
import {
  NCard, NButton, NText, NGrid, NGi, NTag, NSpace, NPopconfirm,
  NDivider, NModal, NForm, NFormItem, NInput, NSelect, NSwitch,
  NDrawer, NDrawerContent, NDataTable, useMessage,
} from 'naive-ui'
import { networkApi, nodeApi } from '../api'

const message = useMessage()
const networks = ref([])
const showAdd = ref(false)
const optimizingId = ref(null)
const form = reactive({ name: '', description: '', sort_by: 'latency', auto_update: true })

const showDetail = ref(false)
const selectedNet = ref(null)
const netNodes = ref([])
const detailLoading = ref(false)
const allNodeOptions = ref([])
const selectedNodeIds = ref([])

const drawerWidth = computed(() => window.innerWidth < 768 ? '100vw' : '620px')

const detailColumns = [
  { title: '节点名称', key: 'name', ellipsis: { tooltip: true } },
  { title: '协议', key: 'protocol', width: 75, render: (row) => h(NTag, { size: 'tiny' }, { default: () => (row.protocol || '').toUpperCase() }) },
  { title: '地区', key: 'ip_country', width: 65, render: (row) => row.ip_country || '—' },
  {
    title: '延迟',
    key: 'latency',
    width: 80,
    render: (row) => {
      const lat = row.real_latency_ms || row.latency_ms
      return lat ? `${Math.round(lat)}ms` : '—'
    },
  },
  {
    title: '移除',
    key: 'remove',
    width: 65,
    render: (row) => h(NButton, { size: 'tiny', type: 'error', quaternary: true, onClick: () => removeNodeFromNet(row) }, { default: () => '移除' }),
  },
]

async function loadNetworks() {
  try {
    const res = await networkApi.list()
    networks.value = res.data
  } catch (e) {
    message.error('加载网络列表失败')
  }
}

async function handleAdd() {
  if (!form.name) { message.warning('请输入名称'); return }
  try {
    await networkApi.create({ ...form })
    message.success('创建成功')
    showAdd.value = false
    form.name = ''; form.description = ''
    loadNetworks()
  } catch (e) {
    message.error('创建失败')
  }
}

async function deleteNetwork(net) {
  try {
    await networkApi.remove(net.id)
    message.success('已删除')
    loadNetworks()
  } catch (e) {
    message.error('删除失败')
  }
}

async function handleSmartSelect(net) {
  if (!net) return
  optimizingId.value = net.id
  try {
    const res = await networkApi.smartSelect(net.id, { max_total: 50, max_per_country: 5, prefer_clean: true })
    message.success(res.data.message)
    loadNetworks()
    if (showDetail.value && selectedNet.value?.id === net.id) {
      openDetail(net)
    }
  } catch (e) {
    message.error('智能优选失败')
  } finally {
    optimizingId.value = null
  }
}

async function resetToken(net) {
  try {
    const res = await networkApi.resetToken(net.id)
    net.token = res.data.token
    message.success('订阅 Token 已重置')
  } catch (e) {
    message.error('重置失败')
  }
}

async function openDetail(net) {
  selectedNet.value = net
  showDetail.value = true
  detailLoading.value = true
  try {
    const [netRes, allRes] = await Promise.all([
      networkApi.getNodes(net.id),
      nodeApi.list({ page_size: 300 }),
    ])
    netNodes.value = netRes.data
    const netNodeIds = new Set(netRes.data.map(n => n.id))
    allNodeOptions.value = allRes.data.items
      .filter(n => !netNodeIds.has(n.id))
      .map(n => ({ label: `[${(n.ip_country || '??').toUpperCase()}] ${n.name}`, value: n.id }))
  } catch (e) {
    message.error('加载节点失败')
  } finally {
    detailLoading.value = false
  }
}

async function handleAddNodes() {
  if (!selectedNodeIds.value.length) { message.warning('请选择节点'); return }
  try {
    await networkApi.addNodes(selectedNet.value.id, selectedNodeIds.value)
    message.success('已添加节点')
    selectedNodeIds.value = []
    openDetail(selectedNet.value)
    loadNetworks()
  } catch (e) {
    message.error('添加失败')
  }
}

async function removeNodeFromNet(node) {
  try {
    await networkApi.removeNode(selectedNet.value.id, node.id)
    message.success('已移除')
    openDetail(selectedNet.value)
    loadNetworks()
  } catch (e) {
    message.error('移除失败')
  }
}

function copySubLink(net, format) {
  const tokenParam = net.token ? `?token=${net.token}` : ''
  const url = `${window.location.origin}/subscribe/${net.id}/${format}${tokenParam}`
  navigator.clipboard.writeText(url).then(() => {
    message.success(`已复制 ${format.toUpperCase()} 专属订阅链接（已含安全 Token）`)
  }).catch(() => {
    message.info(`链接: ${url}`)
  })
}

onMounted(loadNetworks)
</script>
