<template>
  <div>
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

    <n-grid :cols="2" :x-gap="16">
      <n-gi>
        <n-card title="节点状态分布" :bordered="false" style="border-radius:12px">
          <div v-if="nodeStats.total === 0" style="text-align:center; color:#aaa; padding:40px 0">暂无节点数据</div>
          <div v-else>
            <div v-for="item in nodeStatusItems" :key="item.label" class="stat-row">
              <span class="stat-dot" :style="{ background: item.color }"></span>
              <span class="stat-label">{{ item.label }}</span>
              <n-progress
                type="line"
                :percentage="item.pct"
                :color="item.color"
                :rail-color="'#f0f0f0'"
                style="flex:1; margin: 0 12px"
              />
              <span class="stat-count">{{ item.count }}</span>
            </div>
          </div>
        </n-card>
      </n-gi>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { NGrid, NGi, NCard, NStatistic, NProgress, NList, NListItem, NThing, NAvatar } from 'naive-ui'
import { subApi, nodeApi } from '../api'

const subs = ref([])
const nodeStatusData = ref({ total: 0, ok: 0, timeout: 0, error: 0, unknown: 0 })

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

const recentSubs = computed(() => subs.value.slice(0, 5))

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

    // Fetch counts by status
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
  } catch (e) {
    console.error(e)
  }
}

onMounted(loadData)
</script>

<style scoped>
.stat-row { display: flex; align-items: center; margin-bottom: 16px; }
.stat-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.stat-label { width: 50px; font-size: 13px; color: #666; margin-left: 8px; }
.stat-count { font-weight: 600; font-size: 14px; width: 40px; text-align: right; }
</style>
