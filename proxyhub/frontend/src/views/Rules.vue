<template>
  <div>
    <!-- Toolbar -->
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap">
        <n-button type="primary" @click="showAdd = true">➕ 添加规则</n-button>
        <n-button @click="showImport = true">📋 从剪贴板批量导入节点</n-button>
        <n-button
          v-if="checkedIds.length"
          type="error"
          @click="handleBatchDelete"
        >
          🗑 删除选中 ({{ checkedIds.length }})
        </n-button>
        <n-text depth="3" style="margin-left:auto; font-size:13px">共 {{ rules.length }} 条规则 · 优先级数字越小越靠前</n-text>
      </div>
    </n-card>

    <!-- Rules table -->
    <n-card :bordered="false" style="border-radius:12px; margin-bottom:16px">
      <n-data-table
        :columns="columns"
        :data="rules"
        :loading="loading"
        :row-key="(r) => r.id"
        v-model:checked-row-keys="checkedIds"
        striped
        size="small"
        :scroll-x="600"
      />
    </n-card>

    <!-- Info card -->
    <n-card :bordered="false" style="border-radius:12px">
      <n-alert type="info" :show-icon="true">
        <template #header>规则说明</template>
        自定义规则会被优先插入到导出的 Clash 订阅文件顶部（在芙芙模板规则之前生效）。
        <br/>- <b>直连</b>：匹配域名直接连接，不走代理（适合国内网站、内网地址）。
        <br/>- <b>代理</b>：匹配域名强制走代理节点。
        <br/>- <b>拒绝</b>：匹配域名直接拦截（适合广告/追踪域名）。
      </n-alert>
    </n-card>

    <!-- Add Rule Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="添加自定义规则" style="width:480px; border-radius:12px">
      <n-form :model="form" label-placement="left" label-width="90px">
        <n-form-item label="域名/IP">
          <n-input v-model:value="form.pattern" placeholder="例：example.com 或 192.168.0.0/16" />
        </n-form-item>
        <n-form-item label="匹配方式">
          <n-select v-model:value="form.match_type" :options="matchTypeOptions" />
        </n-form-item>
        <n-form-item label="动作">
          <n-radio-group v-model:value="form.rule_type">
            <n-radio value="direct">🌐 直连</n-radio>
            <n-radio value="proxy">🚀 代理</n-radio>
            <n-radio value="reject">⛔ 拒绝</n-radio>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="优先级">
          <n-input-number v-model:value="form.priority" :min="1" :max="999" style="width:100%" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="form.remark" placeholder="可选说明" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <n-button @click="showAdd = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleAdd">添加</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Clipboard Import Modal -->
    <n-modal v-model:show="showImport" preset="card" title="📋 剪贴板批量导入节点" style="width:560px; border-radius:12px">
      <n-space vertical>
        <n-text depth="3" style="font-size:13px">
          支持粘贴任意格式：节点 URI 列表、Base64 编码字符串、混合文本、Clash YAML 等，系统自动识别并解析。
        </n-text>
        <n-button @click="pasteFromClipboard" block>📋 点击从剪贴板读取</n-button>
        <n-input
          v-model:value="importText"
          type="textarea"
          :rows="8"
          placeholder="或直接在此粘贴文本..."
        />
        <div v-if="parsedNodes.length" style="margin-top:8px">
          <n-tag type="success">✅ 识别到 {{ parsedNodes.length }} 个节点</n-tag>
          <n-list style="margin-top:8px; max-height:200px; overflow-y:auto">
            <n-list-item v-for="n in parsedNodes.slice(0,10)" :key="n.name" style="padding:4px 0">
              <n-text style="font-size:12px">{{ n.protocol.toUpperCase() }} · {{ n.name }}</n-text>
            </n-list-item>
            <n-list-item v-if="parsedNodes.length > 10">
              <n-text depth="3" style="font-size:12px">... 以及更多 {{ parsedNodes.length - 10 }} 个</n-text>
            </n-list-item>
          </n-list>
        </div>
        <n-alert v-if="importText && parsedNodes.length === 0 && !parsing" type="warning">
          未识别到有效节点，请检查格式
        </n-alert>
      </n-space>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <n-button @click="showImport = false; importText = ''; parsedNodes = []">取消</n-button>
          <n-button @click="parseImportText" :loading="parsing">🔍 解析</n-button>
          <n-button type="primary" :disabled="!parsedNodes.length" :loading="importing" @click="handleImportNodes">
            ✅ 导入 {{ parsedNodes.length }} 个节点
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, h, reactive, onMounted } from 'vue'
import {
  NCard, NButton, NText, NDataTable, NModal, NForm, NFormItem,
  NInput, NInputNumber, NSelect, NSpace, NTag, NRadioGroup, NRadio,
  NPopconfirm, NAlert, NList, NListItem, useMessage,
} from 'naive-ui'
import { rulesApi, nodeApi } from '../api'

const message = useMessage()
const rules = ref([])
const loading = ref(false)
const checkedIds = ref([])
const showAdd = ref(false)
const showImport = ref(false)
const saving = ref(false)
const importing = ref(false)
const parsing = ref(false)
const importText = ref('')
const parsedNodes = ref([])

const form = reactive({
  pattern: '',
  match_type: 'DOMAIN-SUFFIX',
  rule_type: 'direct',
  priority: 100,
  remark: '',
})

const matchTypeOptions = [
  { label: 'DOMAIN-SUFFIX（域名后缀，如 example.com 匹配所有子域）', value: 'DOMAIN-SUFFIX' },
  { label: 'DOMAIN（精确匹配域名）', value: 'DOMAIN' },
  { label: 'DOMAIN-KEYWORD（包含关键词）', value: 'DOMAIN-KEYWORD' },
  { label: 'IP-CIDR（IP 段，如 192.168.0.0/16）', value: 'IP-CIDR' },
]

function actionTag(type) {
  const map = {
    direct: ['success', '🌐 直连'],
    proxy: ['info', '🚀 代理'],
    reject: ['error', '⛔ 拒绝'],
  }
  const [t, label] = map[type] || ['default', type]
  return h(NTag, { type: t, size: 'small' }, { default: () => label })
}

const columns = [
  { type: 'selection' },
  { title: '优先级', key: 'priority', width: 70, sorter: 'default' },
  { title: '域名/IP', key: 'pattern', ellipsis: { tooltip: true } },
  { title: '匹配方式', key: 'match_type', width: 160 },
  {
    title: '动作',
    key: 'rule_type',
    width: 100,
    render: (row) => actionTag(row.rule_type),
  },
  { title: '备注', key: 'remark', ellipsis: true },
  {
    title: '启用',
    key: 'enabled',
    width: 70,
    render: (row) => h(NTag, { size: 'small', type: row.enabled ? 'success' : 'default' }, { default: () => row.enabled ? '是' : '否' }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) => h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
      trigger: () => h(NButton, { size: 'small', type: 'error' }, { default: () => '删除' }),
      default: () => '确认删除此规则？',
    }),
  },
]

async function loadRules() {
  loading.value = true
  try {
    const res = await rulesApi.list()
    rules.value = res.data
  } catch (e) {
    message.error('加载规则失败')
  } finally {
    loading.value = false
  }
}

async function handleAdd() {
  if (!form.pattern) { message.warning('请填写域名或 IP'); return }
  saving.value = true
  try {
    await rulesApi.create({ ...form })
    message.success('规则已添加')
    showAdd.value = false
    form.pattern = ''; form.remark = ''; form.priority = 100
    loadRules()
  } catch (e) {
    message.error('添加失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await rulesApi.remove(row.id)
    message.success('已删除')
    loadRules()
  } catch (e) {
    message.error('删除失败')
  }
}

async function handleBatchDelete() {
  try {
    await rulesApi.batchDelete(checkedIds.value)
    message.success(`已删除 ${checkedIds.value.length} 条规则`)
    checkedIds.value = []
    loadRules()
  } catch (e) {
    message.error('批量删除失败')
  }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    importText.value = text
    message.success('已读取剪贴板内容')
    await parseImportText()
  } catch (e) {
    message.warning('无法读取剪贴板，请手动粘贴到文本框中')
  }
}

async function parseImportText() {
  if (!importText.value.trim()) { message.warning('请先输入或粘贴文本'); return }
  parsing.value = true
  parsedNodes.value = []
  try {
    const res = await rulesApi.parseText(importText.value)
    parsedNodes.value = res.data.nodes || []
    if (parsedNodes.value.length === 0) {
      message.warning('未识别到有效节点')
    } else {
      message.success(`识别到 ${parsedNodes.value.length} 个节点`)
    }
  } catch (e) {
    message.error('解析失败')
  } finally {
    parsing.value = false
  }
}

async function handleImportNodes() {
  if (!parsedNodes.value.length) return
  importing.value = true
  let success = 0
  try {
    for (const node of parsedNodes.value) {
      try {
        await nodeApi.create({
          name: node.name,
          protocol: node.protocol,
          address: node.address,
          port: node.port,
          raw_config: node.raw_config,
          extra: node.extra,
        })
        success++
      } catch (e) { /* skip individual failures */ }
    }
    message.success(`成功导入 ${success} / ${parsedNodes.value.length} 个节点`)
    showImport.value = false
    importText.value = ''
    parsedNodes.value = []
  } catch (e) {
    message.error('导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(loadRules)
</script>
