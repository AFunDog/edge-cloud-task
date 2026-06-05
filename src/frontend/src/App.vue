<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchState } from './api'
import AgentPanel from './components/AgentPanel.vue'
import DetectionPanel from './components/DetectionPanel.vue'
import HeaderMetrics from './components/HeaderMetrics.vue'
import StatusPanel from './components/StatusPanel.vue'
import TaskLogPanel from './components/TaskLogPanel.vue'
import type { SystemState } from './types'
import { formatTime } from './utils/format'

const state = ref<SystemState | null>(null)
const loading = ref(true)
const error = ref('')
let timer: number | null = null

async function loadState(): Promise<void> {
  try {
    error.value = ''
    state.value = await fetchState()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    loading.value = false
  }
}

const recentDetections = computed(() => state.value?.recent_detections ?? [])
const edgeStatus = computed(() => state.value?.edge_status ?? [])
const taskLogs = computed(() => state.value?.task_logs ?? [])
const latestDetection = computed(() => recentDetections.value[0] || null)
const serverTime = computed(() => formatTime(state.value?.server_time))

onMounted(async () => {
  await loadState()
  timer = window.setInterval(loadState, 3000)
})

onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer)
  }
})
</script>

<template>
  <div class="shell">
    <div class="backdrop backdrop-a"></div>
    <div class="backdrop backdrop-b"></div>

    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Cloud / Orchestration / Insight</p>
        <h1>云端协同控制台</h1>
        <p class="lede">
          这是云端视角的正式控制台，负责展示系统状态、智能体对话、任务日志和云端调度结果；边端的实时姿态工作台独立运行。
        </p>
      </div>
      <HeaderMetrics :error="error" :edge-status="edgeStatus" :recent-detections="recentDetections" />
    </header>

    <main class="grid">
      <section class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="panel-kicker">Live State</p>
            <h2>边端状态与实时检测</h2>
          </div>
          <div class="panel-meta">Server time: {{ serverTime }}</div>
        </div>

        <div v-if="loading" class="state-line">正在拉取系统状态...</div>
        <div v-else-if="error" class="state-line state-error">{{ error }}</div>
        <div v-else class="state-grid">
          <StatusPanel :edge-status="edgeStatus" />
          <DetectionPanel :latest-detection="latestDetection" />
        </div>
      </section>

      <AgentPanel @state-changed="loadState" />
      <TaskLogPanel :task-logs="taskLogs" />
    </main>
  </div>
</template>
