<template>
  <div>
    <!-- Action bar -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="showSmartImport = true">⚡ 智能导入 (NekoBox)</n-button>
        <n-button secondary @click="openAddModal">➕ 手动添加</n-button>
        <n-button quaternary @click="loadSubs">🔄 刷新列表</n-button>
        <n-text depth="3" style="font-size: 13px; margin-left: auto">
          共 {{ subs.length }} 个聚合订阅源
        </n-text>
      </div>
    </n-card>

    <!-- Subscriptions table -->
    <n-card :bordered="false" style="border-radius: 12px">
      <n-data-table
        :columns="columns"
        :data="subs"
        :loading="loading"
        :row-key="(row) => row.id"
        striped
        size="small"
        :scroll-x="720"
      />
    </n-card>

    <!-- Add / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="isEdit ? '编辑订阅' : '添加订阅'" style="max-width: 480px; width: 95vw; border-radius: 12px">
      <n-form :model="form" label-placement="left" label-width="90px">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="留空则自动从链接识别" />
        </n-form-item>
        <n-form-item label="订阅链接">
          <n-input v-model:value="form.url" placeholder="https://..." type="textarea" :rows="3" />
        </n-form-item>
        <n-form-item label="自动刷新">
          <n-switch v-model:value="form.auto_refresh" />
          <span style="margin-left: 8px; font-size: 12px; color: #888">开启后按设定间隔自动拉取</span>
        </n-form-item>
        <n-form-item v-if="form.auto_refresh" label="间隔(分钟)">
          <n-input-number v-model:value="form.interval_minutes" :min="10" :max="1440" :step="60" style="width: 100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSave">
            {{ isEdit ? '保存修改' : '确认添加' }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- Smart Import Modal -->
    <SmartImportModal v-model:show="showSmartImport" @imported="loadSubs" />
  </div>
</template>

<script setup>
import { ref, h, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NModal, NForm, NFormItem,
  NInput, NInputNumber, NSwitch, NTag, NSpace, NPopconfirm, useMessage,
} from 'naive-ui'
import { subApi } from '../api'
import SmartImportModal from '../components/SmartImportModal.vue'

const message = useMessage()
const subs = ref([])
const loading = ref(false)
const showSmartImport = ref(false)
const showModal = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const saving = ref(false)
const refreshingIds = ref(new Set())

const form = ref({
  name: '',
  url: '',
  auto_refresh: true,
  interval_minutes: 360,
})

const columns = [
  {
    title: '名称',
    key: 'name',
    width: 150,
    render: (row) => h('div', { style: 'font-weight: 600' }, row.name || '未命名订阅'),
  },
  {
    title: '订阅链接',
    key: 'url',
    ellipsis: { tooltip: true },
  },
  {
    title: '节点数',
    key: 'node_count',
    width: 95,
    render: (row) => h(NTag, {
      type: row.node_count > 0 ? 'success' : 'default',
      size: 'small',
      bordered: false,
    }, { default: () => `${row.node_count || 0} 节点` }),
  },
  {
    title: '自动刷新',
    key: 'auto_refresh',
    width: 100,
    render: (row) => row.auto_refresh
      ? h(NTag, { type: 'info', size: 'tiny' }, { default: () => `${row.interval_minutes}m` })
      : h(NTag, { size: 'tiny', bordered: false }, { default: () => '关闭' }),
  },
  {
    title: '最后更新',
    key: 'last_fetched',
    width: 140,
    render: (row) => row.last_fetched
      ? new Date(row.last_fetched).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      : '未拉取',
  },
  {
    title: '操作',
    key: 'actions',
    width: 170,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, {
          size: 'small',
          quaternary: true,
          loading: refreshingIds.value.has(row.id),
          onClick: () => handleRefresh(row),
        }, { default: () => '🔄 刷新' }),
        h(NButton, {
          size: 'small',
          quaternary: true,
          onClick: () => openEditModal(row),
        }, { default: () => '✏️ 编辑' }),
        h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error', quaternary: true }, { default: () => '删除' }),
          default: () => `确认删除订阅【${row.name}】及其所有节点？`,
        }),
      ],
    }),
  },
]

async function loadSubs() {
  loading.value = true
  try {
    const res = await subApi.list()
    subs.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    message.error('加载订阅列表失败')
  } finally {
    loading.value = false
  }
}

function openAddModal() {
  isEdit.value = false
  editingId.value = null
  form.value = { name: '', url: '', auto_refresh: true, interval_minutes: 360 }
  showModal.value = true
}

function openEditModal(row) {
  isEdit.value = true
  editingId.value = row.id
  form.value = {
    name: row.name,
    url: row.url,
    auto_refresh: row.auto_refresh,
    interval_minutes: row.interval_minutes || 360,
  }
  showModal.value = true
}

async function handleSave() {
  if (!form.value.url) {
    message.warning('请填写订阅链接')
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await subApi.update(editingId.value, form.value)
      message.success('订阅已更新')
    } else {
      await subApi.create(form.value)
      message.success('已添加，正在后台拉取节点...')
    }
    showModal.value = false
    setTimeout(loadSubs, 2000)
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleRefresh(row) {
  refreshingIds.value.add(row.id)
  try {
    await subApi.refresh(row.id)
    message.success(`已触发【${row.name}】后台刷新`)
    setTimeout(async () => {
      await loadSubs()
      refreshingIds.value.delete(row.id)
    }, 3000)
  } catch (e) {
    refreshingIds.value.delete(row.id)
    message.error('刷新失败')
  }
}

async function handleDelete(row) {
  try {
    await subApi.remove(row.id)
    message.success('已删除订阅及关联节点')
    loadSubs()
  } catch (e) {
    message.error('删除失败')
  }
}

onMounted(loadSubs)
</script>
