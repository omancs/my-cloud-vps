<template>
  <div>
    <!-- Action bar -->
    <n-card :bordered="false" style="border-radius: 12px; margin-bottom: 16px">
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="showSmartImport = true">⚡ 智能导入 (NekoBox)</n-button>
        <n-button secondary @click="showManualAdd = true">➕ 手动添加</n-button>
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
        :pagination="{ pageSize: 20 }"
        row-key="id"
        striped
        :scroll-x="700"
      />
    </n-card>

    <!-- Manual Add Modal -->
    <n-modal v-model:show="showManualAdd" preset="card" title="手动添加订阅" style="max-width: 480px; width: 95vw; border-radius: 12px">
      <n-form :model="form" label-placement="left" label-width="90px">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="留空则自动从链接识别" />
        </n-form-item>
        <n-form-item label="订阅链接">
          <n-input v-model:value="form.url" placeholder="https://..." type="textarea" :rows="3" />
        </n-form-item>
        <n-form-item label="自动刷新">
          <n-switch v-model:value="form.auto_refresh" />
          <span style="margin-left: 8px; font-size: 12px; color: #888">每 6 小时自动更新节点</span>
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px">
          <n-button @click="showManualAdd = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleManualAdd">确认添加</n-button>
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
  NInput, NSwitch, NTag, NSpace, NPopconfirm, useMessage,
} from 'naive-ui'
import { subApi } from '../api'
import SmartImportModal from '../components/SmartImportModal.vue'

const message = useMessage()
const subs = ref([])
const loading = ref(false)
const showSmartImport = ref(false)
const showManualAdd = ref(false)
const saving = ref(false)

const form = ref({
  name: '',
  url: '',
  auto_refresh: true,
  interval_minutes: 360,
})

const columns = [
  { title: '名称', key: 'name', width: 140 },
  { title: '订阅链接', key: 'url', ellipsis: { tooltip: true } },
  {
    title: '节点数',
    key: 'node_count',
    width: 90,
    render: (row) => h(NTag, { type: row.node_count > 0 ? 'success' : 'default', size: 'small' }, { default: () => `${row.node_count} 节点` }),
  },
  {
    title: '最后更新',
    key: 'last_fetched',
    width: 150,
    render: (row) => row.last_fetched ? new Date(row.last_fetched).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未更新',
  },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'small', quaternary: true, onClick: () => handleRefresh(row) }, { default: () => '🔄 刷新' }),
        h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error', quaternary: true }, { default: () => '删除' }),
          default: () => '确认删除此订阅及其所属节点？',
        }),
      ],
    }),
  },
]

async function loadSubs() {
  loading.value = true
  try {
    const res = await subApi.list()
    subs.value = res.data
  } catch (e) {
    message.error('加载订阅列表失败')
  } finally {
    loading.value = false
  }
}

async function handleManualAdd() {
  if (!form.value.url) {
    message.warning('请填写订阅链接')
    return
  }
  saving.value = true
  try {
    await subApi.create(form.value)
    message.success('已添加，正在后台拉取节点...')
    showManualAdd.value = false
    form.value = { name: '', url: '', auto_refresh: true, interval_minutes: 360 }
    setTimeout(loadSubs, 2500)
  } catch (e) {
    message.error(e.response?.data?.detail || '添加失败')
  } finally {
    saving.value = false
  }
}

async function handleRefresh(row) {
  try {
    await subApi.refresh(row.id)
    message.success('已提交后台刷新')
    setTimeout(loadSubs, 3000)
  } catch (e) {
    message.error('刷新失败')
  }
}

async function handleDelete(row) {
  try {
    await subApi.remove(row.id)
    message.success('已删除')
    loadSubs()
  } catch (e) {
    message.error('删除失败')
  }
}

onMounted(loadSubs)
</script>
