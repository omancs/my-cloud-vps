<template>
  <div>
    <!-- Stats cards -->
    <n-grid :cols="4" :x-gap="16" :y-gap="16" style="margin-bottom: 24px">
      <n-gi v-for="stat in stats" :key="stat.label">
        <n-card :bordered="false" style="border-radius:12px">
          <n-statistic :label="stat.label" :value="stat.value">
            <template #prefix>
              <span style="font-size:20px; margin-right:8px">{{ stat.icon }}</span>
            </template>
          </n-statistic>
        </n-card>
      </n-gi>
    </n-grid>

    <n-grid :cols="3" :x-gap="16" style="margin-bottom:16px">
      <!-- Traffic Monitor Card -->
      <n-gi>
        <n-card title="📶 本月流量监控" :bordered="false" style="border-radius:12px; height:100%">
          <template #header-extra>
            <n-button size="tiny" @click="showTrafficConfig = true">⚙️ 配置</n-button>
          </template>
          <div v-if="trafficData">
            <div style="text-align:center; margin-bottom:16px">
              <n-progress
                type="circle"
                :percentage="trafficData.usage_pct"
                :color="trafficColor"
                :rail-color="'#f0f0f0'"
                :stroke-width="10"
              >
                <div>
                  <div style="font-size:18px; font-weight:700">{{ trafficData.usage_pct }}%</div>
                  <div style="font-size:11px; color:#888">已使用</div>
                </div>
              </n-progress>
            </div>
            <n-descriptions :column="1" size="small">
              <n-descriptions-item label="已用流量">{{ trafficData.used_gb }} GB</n-descriptions-item>
              <n-descriptions-item label="月度额度">{{ trafficData.quota_gb }} GB</n-descriptions-item>
              <n-descriptions-item label="剩余流量">{{ trafficData.remaining_gb }} GB</n-descriptions-item>
              <n-descriptions-item label="监控网卡">{{ trafficData.interface }}</n-descriptions-item>
            </n-descriptions>
            <n-alert v-if="trafficData.alert === 'exceeded'" type="error" style="margin-top:8px" :show-icon="false">
              ⚠️ 已超出月度额度！
            </n-alert>
            <n-alert v-else-if="trafficData.alert === 'warning'" type="warning" style="margin-top:8px" :show-icon="false">
              ⚠️ 流量使用已超过 {{ trafficData.alert_threshold_pct }}%
            </n-alert>
          </div>
          <div v-else style="text-align:center; color:#aaa; padding:40px 0">
            <div>加载中...</div>
          </div>
        </n-card>
      </n-gi>

      <!-- Node status -->
      <n-gi>
        <n-card title="节点状态分布" :bordered="false" style="border-radius:12px">
          <div v-if="nodeStats.total === 0" style="text-align:center; color:#aaa; padding:40px 0">暂无节点数据</div>
          <div v-else>
            <div v-for="item in nodeStatusItems" :key="item.label" class="stat-row">
              <span class="stat-dot" :style="{ background: item.color }"></span>
              <span class="stat-label">{{ item.label }}</span>
              <n-progress type="line" :percentage="item.pct" :color="item.color" :rail-color="'#f0f0f0'" style="flex:1; margin: 0 12px" />
              <span class="stat-count">{{ item.count }}</span>
            </div>
          </div>
        </n-card>
      </n-gi>

      <!-- Recent subscriptions -->
      <n-gi>
        <n-card title="最近订阅" :bordered="false" style="border-radius:12px">
          <n-list>
            <n-list-item v-for="sub in recentSubs" :key="sub.id">
              <n-thing :title="sub.name" :description="`${sub.node_count} 个节点 · ${formatTime(sub.last_fetched)}`">
                <template #avatar>
                  <n-avatar round style="background:#6366f1">{{ sub.name[0] }}</n-avatar>
                </template>
              </n-thing>
            </n-list-item>
            <div v-if="!recentSubs.length" style="text-align:center; color:#aaa; padding:20px 0">暂无订阅</div>
          </n-list>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- Traffic Config Modal -->
    <n-modal v-model:show="showTrafficConfig" preset="card" title="⚙️ 流量监控配置" style="width:420px; border-radius:12px">
      <n-form :model="trafficForm" label-placement="left" label-width="100px">
        <n-form-item label="网卡名称">
          <n-input v-model:value="trafficForm.interface" placeholder="如 eth0 / ens4" />
        </n-form-item>
        <n-form-item label="月度额度 (GB)">
          <n-input-number v-model:value="trafficForm.monthly_quota_gb" :min="0.1" :step="0.5" style="width:100%" />
        </n-form-item>
        <n-form-item label="告警阈值 (%)">
          <n-input-number v-model:value="trafficForm.alert_threshold_pct" :min="50" :max="100" style="width:100%" />
        </n-form-item>
        <n-form-item label="每月重置日">
          <n-input-number v-model:value="trafficForm.reset_day" :min="1" :max="28" style="width:100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <n-button @click="showTrafficConfig = false">取消</n-button>
          <n-button type="primary" @click="saveTrafficConfig">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import {
  NGrid, NGi, NCard, NStatistic, NProgress, NList, NListItem, NThing,
  NAvatar, NAlert, NModal, NForm, NFormItem, NInput, NInputNumber,
  NButton, NDescriptions, NDescriptionsItem, useMessage,
} from 'naive-ui'
import { subApi, nodeApi, trafficApi } from '../api'

const message = useMessage()
const subs = ref([])
const nodeStatusData = ref({ total: 0, ok: 0, timeout: 0, error: 0, unknown: 0 })
const trafficData = ref(null)
const showTrafficConfig = ref(false)
const trafficForm = reactive({ interface: 'eth0', monthly_quota_gb: 1, alert_threshold_pct: 80, reset_day: 1 })

const stats = computed(() => [
  { label: '订阅数量', value: subs.value.length, icon: '📋' },
  { label: '节点总数', value: nodeStatusData.value.total, icon: '🌐' },
  { label: '可用节点', value: nodeStatusData.value.ok, icon: '✅' },
  { label: '失效节点', value: nodeStatusData.value.timeout + nodeStatusData.value.error, icon: '❌' },
])

const nodeStats = computed(() => nodeStatusData.value)

const nodeStatusItems = computed(() => {
  const t = nodeStatusData.value.total || 1
  return [
    { label: '正常', count: nodeStatusData.value.ok, color: '#18a058', pct: Math.round(nodeStatusData.value.ok / t * 100) },
    { label: '超时', count: nodeStatusData.value.timeout, color: '#f0a020', pct: Math.round(nodeStatusData.value.timeout / t * 100) },
    { label: '未测试', count: nodeStatusData.value.unknown, color: '#909399', pct: Math.round(nodeStatusData.value.unknown / t * 100) },
  ]
})

const recentSubs = computed(() => subs.value.slice(0, 4))

const trafficColor = computed(() => {
  if (!trafficData.value) return '#6366f1'
  const pct = trafficData.value.usage_pct
  if (pct >= 100) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
})

function formatTime(t) {
  if (!t) return '未刷新'
  return new Date(t).toLocaleString('zh-CN')
}

async function loadData() {
  try {
    const subRes = await subApi.list()
    subs.value = subRes.data

    const nodeRes = await nodeApi.list({ page_size: 1 })
    const total = nodeRes.data.total

    const [ok, timeout, error] = await Promise.all([
      nodeApi.list({ status: 'ok', page_size: 1 }),
      nodeApi.list({ status: 'timeout', page_size: 1 }),
      nodeApi.list({ status: 'error', page_size: 1 }),
    ])
    nodeStatusData.value = {
      total,
      ok: ok.data.total,
      timeout: timeout.data.total,
      error: error.data.total,
      unknown: total - ok.data.total - timeout.data.total - error.data.total,
    }
  } catch (e) { console.error(e) }
}

async function loadTraffic() {
  try {
    const res = await trafficApi.usage()
    trafficData.value = res.data
  } catch (e) { /* ignore */ }
}

async function loadTrafficConfig() {
  try {
    const res = await trafficApi.config()
    const c = res.data
    trafficForm.interface = c.interface
    trafficForm.monthly_quota_gb = c.monthly_quota_gb
    trafficForm.alert_threshold_pct = c.alert_threshold_pct
    trafficForm.reset_day = c.reset_day
  } catch (e) { /* ignore */ }
}

async function saveTrafficConfig() {
  try {
    await trafficApi.updateConfig({ ...trafficForm })
    message.success('配置已保存')
    showTrafficConfig.value = false
    loadTraffic()
  } catch (e) {
    message.error('保存失败')
  }
}

onMounted(() => {
  loadData()
  loadTraffic()
  loadTrafficConfig()
})
</script>

<style scoped>
.stat-row { display: flex; align-items: center; margin-bottom: 16px; }
.stat-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.stat-label { width: 50px; font-size: 13px; color: #666; margin-left: 8px; }
.stat-count { font-weight: 600; font-size: 14px; width: 40px; text-align: right; }
</style>
