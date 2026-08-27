<template>
  <div>
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <div style="display:flex; gap:12px">
        <n-button type="primary" @click="showAdd = true">➕ 创建网络分组</n-button>
      </div>
    </n-card>

    <n-grid :cols="2" :x-gap="16" :y-gap="16">
      <n-gi v-for="net in networks" :key="net.id">
        <n-card :bordered="false" style="border-radius:12px">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <div>
                <span style="font-size:16px; font-weight:600">{{ net.name }}</span>
                <n-tag size="small" type="info" style="margin-left:8px">{{ net.node_count }} 节点</n-tag>
              </div>
              <n-space>
                <n-button size="small" @click="openDetail(net)">管理节点</n-button>
                <n-popconfirm @positive-click="deleteNetwork(net)">
                  <template #trigger>
                    <n-button size="small" type="error">删除</n-button>
                  </template>
                  确认删除网络分组？
                </n-popconfirm>
              </n-space>
            </div>
          </template>
          <n-text depth="3">{{ net.description || '暂无描述' }}</n-text>
          <n-divider style="margin:12px 0" />
          <div style="display:flex; gap:8px; flex-wrap:wrap">
            <n-tag size="small">排序：{{ net.sort_by === 'latency' ? 'TCP延迟' : '代理延迟' }}</n-tag>
            <n-tag size="small">创建：{{ new Date(net.created_at).toLocaleDateString('zh-CN') }}</n-tag>
          </div>
          <n-divider style="margin:12px 0" />
          <div style="display:flex; gap:8px">
            <n-button size="small" block @click="copySubLink(net.id, 'clash')">📋 Clash 订阅</n-button>
            <n-button size="small" block @click="copySubLink(net.id, 'v2ray')">📋 V2Ray 订阅</n-button>
          </div>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- Add Network Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="创建网络分组" style="width:440px; border-radius:12px">
      <n-form :model="form" label-placement="left" label-width="80px">
        <n-form-item label="名称"><n-input v-model:value="form.name" placeholder="例：家用宽带" /></n-form-item>
        <n-form-item label="描述"><n-input v-model:value="form.description" placeholder="可选描述" /></n-form-item>
        <n-form-item label="排序方式">
          <n-select v-model:value="form.sort_by" :options="[{label:'TCP延迟',value:'latency'},{label:'代理延迟',value:'real_latency'}]" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <n-button @click="showAdd=false">取消</n-button>
          <n-button type="primary" @click="handleAdd">创建</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Network Detail / Node Management Drawer -->
    <n-drawer v-model:show="showDetail" :width="600" placement="right">
      <n-drawer-content :title="selectedNet?.name + ' · 节点管理'" closable>
        <div style="margin-bottom:12px; display:flex; gap:8px">
          <n-select
            v-model:value="selectedNodeIds"
            multiple
            filterable
            :options="allNodeOptions"
            placeholder="选择节点添加到分组"
            style="flex:1"
          />
          <n-button type="primary" @click="handleAddNodes">添加</n-button>
        </div>
        <n-data-table
          :columns="detailColumns"
          :data="netNodes"
          :loading="detailLoading"
          size="small"
          striped
        />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { ref, h, reactive, onMounted } from 'vue'
import {
  NCard, NButton, NText, NGrid, NGi, NTag, NSpace, NPopconfirm,
  NDivider, NModal, NForm, NFormItem, NInput, NSelect, NDrawer,
  NDrawerContent, NDataTable, useMessage,
} from 'naive-ui'
import { networkApi, nodeApi } from '../api'

const message = useMessage()
const networks = ref([])
const showAdd = ref(false)
const form = reactive({ name: '', description: '', sort_by: 'latency' })

const showDetail = ref(false)
const selectedNet = ref(null)
const netNodes = ref([])
const detailLoading = ref(false)
const allNodeOptions = ref([])
const selectedNodeIds = ref([])

const detailColumns = [
  { title: '名称', key: 'name', ellipsis: { tooltip: true } },
  { title: '协议', key: 'protocol', width: 80 },
  { title: '地址', key: 'address', ellipsis: true },
  { title: 'TCP延迟', key: 'latency_ms', width: 90, render: (row) => row.latency_ms ? `${Math.round(row.latency_ms)}ms` : '—' },
  {
    title: '移除',
    key: 'remove',
    width: 70,
    render: (row) => h(NButton, { size: 'small', type: 'error', onClick: () => removeNodeFromNet(row) }, { default: () => '移除' }),
  },
]

async function loadNetworks() {
  try {
    const res = await networkApi.list()
    networks.value = res.data
  } catch (e) {
    message.error('加载失败')
  }
}

async function handleAdd() {
  if (!form.name) { message.warning('请输入名称'); return }
  try {
    await networkApi.create({ ...form })
    message.success('创建成功')
    showAdd.value = false
    form.name = ''; form.description = ''; form.sort_by = 'latency'
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

async function openDetail(net) {
  selectedNet.value = net
  showDetail.value = true
  detailLoading.value = true
  try {
    const [netRes, allRes] = await Promise.all([
      networkApi.getNodes(net.id),
      nodeApi.list({ page_size: 200 }),
    ])
    netNodes.value = netRes.data
    const netNodeIds = new Set(netRes.data.map(n => n.id))
    allNodeOptions.value = allRes.data.items
      .filter(n => !netNodeIds.has(n.id))
      .map(n => ({ label: `${n.name} (${n.address}:${n.port})`, value: n.id }))
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
    message.success('添加成功')
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

function copySubLink(networkId, format) {
  const url = `${window.location.origin}/subscribe/${networkId}/${format}`
  navigator.clipboard.writeText(url).then(() => {
    message.success(`已复制 ${format.toUpperCase()} 订阅链接`)
  })
}

onMounted(loadNetworks)
</script>
