<template>
  <div>
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <div style="display:flex; gap:12px; align-items:center">
        <n-button type="primary" @click="showAdd = true">➕ 添加订阅</n-button>
        <n-text depth="3" style="font-size:13px">共 {{ subs.length }} 个订阅</n-text>
      </div>
    </n-card>

    <n-card :bordered="false" style="border-radius:12px">
      <n-data-table
        :columns="columns"
        :data="subs"
        :loading="loading"
        :pagination="{ pageSize: 20 }"
        row-key="id"
        striped
      />
    </n-card>

    <!-- Add Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="添加订阅" style="width:480px; border-radius:12px">
      <n-form :model="form" label-placement="left" label-width="80px">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="留空则自动从订阅链接识别" />
        </n-form-item>
        <n-form-item label="订阅链接">
          <n-space vertical style="width:100%">
            <n-input v-model:value="form.url" placeholder="https://..." type="textarea" :rows="3" />
            <n-button size="small" @click="pasteUrl">📋 从剪贴板粘贴链接</n-button>
          </n-space>
        </n-form-item>
        <n-form-item label="自动刷新">
          <n-switch v-model:value="form.auto_refresh" />
        </n-form-item>
        <n-form-item v-if="form.auto_refresh" label="间隔(分钟)">
          <n-input-number v-model:value="form.interval_minutes" :min="10" :max="1440" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <n-button @click="showAdd = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleAdd">确认添加</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, h, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NModal, NForm, NFormItem,
  NInput, NInputNumber, NSwitch, NTag, NSpace, NPopconfirm,
  useMessage,
} from 'naive-ui'
import { subApi } from '../api'

const message = useMessage()
const subs = ref([])
const loading = ref(false)
const showAdd = ref(false)
const saving = ref(false)

const form = ref({
  name: '',
  url: '',
  auto_refresh: true,
  interval_minutes: 360,
})

async function pasteUrl() {
  try {
    const text = await navigator.clipboard.readText()
    form.value.url = text.trim()
    message.success('已从剪贴板读取链接')
  } catch (e) {
    message.warning('无法读取剪贴板，请手动粘贴')
  }
}

function statusTag(row) {
  if (!row.last_fetched) return h(NTag, { type: 'default', size: 'small' }, { default: () => '未拉取' })
  return h(NTag, { type: 'success', size: 'small' }, { default: () => `${row.node_count} 节点` })
}

const columns = [
  { title: '名称', key: 'name', width: 150 },
  { title: '订阅链接', key: 'url', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) => statusTag(row),
  },
  {
    title: '自动刷新',
    key: 'auto_refresh',
    width: 90,
    render: (row) => row.auto_refresh ? h(NTag, { type: 'info', size: 'small' }, { default: () => `${row.interval_minutes}分钟` }) : h(NTag, { size: 'small' }, { default: () => '关闭' }),
  },
  {
    title: '最后更新',
    key: 'last_fetched',
    width: 160,
    render: (row) => row.last_fetched ? new Date(row.last_fetched).toLocaleString('zh-CN') : '—',
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row) => h(NSpace, {}, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => handleRefresh(row) }, { default: () => '🔄 刷新' }),
        h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error' }, { default: () => '删除' }),
          default: () => '确认删除此订阅及其节点？',
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
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleAdd() {
  if (!form.value.name || !form.value.url) {
    message.warning('请填写名称和订阅链接')
    return
  }
  saving.value = true
  try {
    await subApi.create(form.value)
    message.success('添加成功，正在后台拉取节点...')
    showAdd.value = false
    form.value = { name: '', url: '', auto_refresh: true, interval_minutes: 360 }
    setTimeout(loadSubs, 2000)
  } catch (e) {
    message.error(e.response?.data?.detail || '添加失败')
  } finally {
    saving.value = false
  }
}

async function handleRefresh(row) {
  try {
    await subApi.refresh(row.id)
    message.success('正在后台刷新...')
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
