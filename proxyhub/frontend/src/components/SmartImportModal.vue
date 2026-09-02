<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="⚡ NekoBox 智能统一导入"
    style="max-width: 600px; width: 95vw; border-radius: 14px"
    :segmented="{ content: 'soft', footer: 'soft' }"
  >
    <n-space vertical size="medium">
      <n-alert type="info" :show-icon="false" style="border-radius: 8px">
        💡 <b>支持粘贴任意内容</b>：订阅链接（HTTP/HTTPS）、节点 URI 列表（vmess/vless/ss/trojan/hy2）、Base64 密文或 Clash YAML 配置，系统自动识别！
      </n-alert>

      <div style="display: flex; gap: 8px; flex-wrap: wrap">
        <n-button type="primary" secondary style="flex: 1; min-width: 140px" @click="pasteFromClipboard">
          📋 从剪贴板一键读取
        </n-button>
        <n-upload
          :show-file-list="false"
          accept=".yaml,.yml,.txt,.json,.conf"
          :custom-request="handleFileUpload"
          style="flex: 1; min-width: 140px"
        >
          <n-button secondary type="info" block>
            📁 上传本地 YAML/文本文件
          </n-button>
        </n-upload>
        <n-button v-if="rawText" @click="clearInput">
          清空
        </n-button>
      </div>

      <n-input
        v-model:value="rawText"
        type="textarea"
        :rows="5"
        placeholder="在此粘贴任意订阅链接、节点链接或 Base64 编码字符串..."
        @update:value="onTextInput"
      />

      <!-- Detection result area -->
      <div v-if="analyzing" style="text-align: center; padding: 12px 0">
        <n-spin size="small" /> <span style="margin-left: 8px; font-size: 13px; color: #888">正在智能识别内容格式...</span>
      </div>

      <!-- Case 1: Detected as Subscription URL -->
      <div v-else-if="resultType === 'subscription_url'" class="result-box sub-box">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px">
          <n-tag type="info" size="small">🔗 识别为：外部聚合订阅链接</n-tag>
        </div>
        <n-form label-placement="left" label-width="80px" size="small">
          <n-form-item label="订阅名称">
            <n-input v-model:value="subName" placeholder="订阅名称（已自动解析）" />
          </n-form-item>
          <n-form-item label="自动刷新">
            <n-switch v-model:value="autoRefresh" />
            <span style="margin-left: 8px; font-size: 12px; color: #888">开启每 6 小时自动更新节点</span>
          </n-form-item>
        </n-form>
      </div>

      <!-- Case 2: Detected as Node List -->
      <div v-else-if="resultType === 'nodes' && parsedNodes.length > 0" class="result-box node-box">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px">
          <n-tag type="success" size="small">🌐 识别到 {{ parsedNodes.length }} 个节点（已自动去重）</n-tag>
        </div>
        <n-scrollbar style="max-height: 160px; padding-right: 6px">
          <n-list size="small">
            <n-list-item v-for="(n, idx) in parsedNodes" :key="idx" style="padding: 4px 0">
              <div style="display: flex; align-items: center; gap: 8px; font-size: 13px">
                <n-tag size="tiny" :type="getProtocolTagType(n.protocol)">{{ (n.protocol || '').toUpperCase() }}</n-tag>
                <span class="ellipsis" style="flex: 1">{{ n.name }}</span>
                <span style="font-size: 11px; color: #999">{{ n.address }}:{{ n.port }}</span>
              </div>
            </n-list-item>
          </n-list>
        </n-scrollbar>
      </div>

      <!-- Case 3: Empty or invalid -->
      <n-alert v-else-if="rawText.trim() && !analyzing" type="warning" :show-icon="false" style="border-radius: 8px">
        ⚠️ 未能从输入文本中解析出有效的订阅链接或节点，请检查内容是否完整。
      </n-alert>
    </n-space>

    <template #footer>
      <div style="display: flex; justify-content: flex-end; gap: 8px">
        <n-button @click="visible = false">取消</n-button>
        <n-button
          type="primary"
          :disabled="!canSubmit"
          :loading="submitting"
          @click="handleSubmit"
        >
          {{ submitButtonText }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  NModal, NSpace, NAlert, NButton, NInput, NSpin, NTag, NForm,
  NFormItem, NSwitch, NScrollbar, NList, NListItem, NUpload, useMessage,
} from 'naive-ui'
import { rulesApi, subApi, nodeApi } from '../api'

const props = defineProps({
  show: { type: Boolean, default: false },
})
const emit = defineEmits(['update:show', 'imported'])

const message = useMessage()

async function handleFileUpload({ file }) {
  analyzing.value = true
  resultType.value = null
  parsedNodes.value = []
  rawText.value = `[本地文件: ${file.name} (${(file.file.size / 1024).toFixed(1)} KB)]`
  message.info(`正在解析文件【${file.name}】...`)
  try {
    const res = await rulesApi.parseFile(file.file)
    resultType.value = res.data.type
    if (res.data.type === 'nodes') {
      parsedNodes.value = res.data.nodes || []
      message.success(`成功识别到 ${parsedNodes.value.length} 个节点！`)
    } else if (res.data.type === 'subscription_url') {
      subUrl.value = res.data.url
      subName.value = res.data.auto_name || file.name
      parsedNodes.value = []
    }
  } catch (e) {
    message.error(e.response?.data?.detail || '文件解析失败，请检查格式')
    resultType.value = null
    parsedNodes.value = []
  } finally {
    analyzing.value = false
  }
}

const visible = computed({
  get: () => props.show,
  set: (v) => emit('update:show', v),
})

const rawText = ref('')
const analyzing = ref(false)
const submitting = ref(false)

const resultType = ref(null) // 'subscription_url' | 'nodes' | null
const subUrl = ref('')
const subName = ref('')
const autoRefresh = ref(true)
const parsedNodes = ref([])

let debounceTimer = null

function getProtocolTagType(proto) {
  const p = (proto || '').toLowerCase()
  if (p === 'vmess') return 'primary'
  if (p === 'vless') return 'info'
  if (p === 'ss') return 'warning'
  if (p === 'trojan') return 'error'
  if (p === 'hy2' || p === 'hysteria2') return 'success'
  return 'default'
}

function clearInput() {
  rawText.value = ''
  resultType.value = null
  parsedNodes.value = []
  subUrl.value = ''
  subName.value = ''
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (!text || !text.trim()) {
      message.warning('剪贴板为空')
      return
    }
    rawText.value = text.trim()
    message.success('已读取剪贴板')
    analyzeContent()
  } catch (e) {
    message.warning('浏览器限制读取剪贴板，请直接在文本框粘贴')
  }
}

function onTextInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(analyzeContent, 400)
}

async function analyzeContent() {
  const txt = rawText.value.trim()
  if (!txt) {
    resultType.value = null
    parsedNodes.value = []
    return
  }

  analyzing.value = true
  try {
    const res = await rulesApi.parseText(txt)
    resultType.value = res.data.type
    if (res.data.type === 'subscription_url') {
      subUrl.value = res.data.url
      subName.value = res.data.auto_name || '外部订阅'
      parsedNodes.value = []
    } else {
      parsedNodes.value = res.data.nodes || []
    }
  } catch (e) {
    resultType.value = null
    parsedNodes.value = []
  } finally {
    analyzing.value = false
  }
}

const canSubmit = computed(() => {
  if (resultType.value === 'subscription_url' && subUrl.value) return true
  if (resultType.value === 'nodes' && parsedNodes.value.length > 0) return true
  return false
})

const submitButtonText = computed(() => {
  if (resultType.value === 'subscription_url') return '保存并拉取订阅'
  if (resultType.value === 'nodes') return `导入 ${parsedNodes.value.length} 个节点`
  return '确认导入'
})

async function handleSubmit() {
  submitting.value = true
  try {
    if (resultType.value === 'subscription_url') {
      await subApi.create({
        name: subName.value || '外部订阅',
        url: subUrl.value,
        auto_refresh: autoRefresh.value,
        interval_minutes: 360,
      })
      message.success('订阅已添加，正在后台拉取节点...')
    } else if (resultType.value === 'nodes') {
      const res = await nodeApi.batchCreate(parsedNodes.value)
      message.success(res.data.message || `成功导入 ${parsedNodes.value.length} 个节点！`)
    }

    visible.value = false
    clearInput()
    emit('imported')
  } catch (e) {
    message.error(e.response?.data?.detail || '导入失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.result-box {
  border-radius: 8px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.02);
  border: 1px dashed rgba(0, 0, 0, 0.1);
}
.ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
