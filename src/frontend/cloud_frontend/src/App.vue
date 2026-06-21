<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchEventReport, fetchState, scheduleTask, sendAgentChat } from './api'
import type {
  CloudAnalysisResponse,
  Detection,
  DetectionResult,
  EventReport,
  SafetyEvent,
  SystemState,
  TaskLog,
} from './types'
import { formatNumber, formatTime } from './utils/format'
import {
  COCO_SKELETON,
  isKeypointVisible,
  normalizeKeypoint,
  type NormalizedKeypoint,
  type SkeletonEdge,
} from './utils/pose'

const state = ref<SystemState | null>(null)
const loading = ref(true)
const error = ref('')
const chatQuestion = ref('请分析当前边缘端画面是否存在异常，并给出调度建议。')
const deviceId = ref('edge-camera-01')
const taskText = ref('姿态识别')
const chatResult = ref<any>(null)
const scheduleResult = ref<any>(null)
const selectedReport = ref<EventReport | null>(null)
const reportError = ref('')
const stageRef = ref<HTMLElement | null>(null)
const stageSize = ref({ width: 0, height: 0 })
let timer: number | null = null
let stageResizeObserver: ResizeObserver | null = null

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

async function submitChat(): Promise<void> {
  try {
    error.value = ''
    chatResult.value = await sendAgentChat({
      question: chatQuestion.value,
      device_id: deviceId.value,
      context: { source: 'web-console' },
    })
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  }
}

async function submitSchedule(): Promise<void> {
  try {
    error.value = ''
    scheduleResult.value = await scheduleTask({
      task: taskText.value,
      device_id: deviceId.value,
      context: {},
    })
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  }
}

async function openReport(event: SafetyEvent): Promise<void> {
  try {
    reportError.value = ''
    selectedReport.value = await fetchEventReport(event.event_id)
  } catch (exc) {
    reportError.value = exc instanceof Error ? exc.message : String(exc)
  }
}

function exportReport(report: EventReport): void {
  const blob = new Blob([report.report_markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `event-${report.event.event_id}.md`
  link.click()
  URL.revokeObjectURL(url)
}

function updateStageSize(): void {
  if (!stageRef.value) return
  const rect = stageRef.value.getBoundingClientRect()
  stageSize.value = { width: rect.width, height: rect.height }
}

function observeStageSize(): void {
  updateStageSize()
  if (!stageRef.value) return
  stageResizeObserver = new ResizeObserver(updateStageSize)
  stageResizeObserver.observe(stageRef.value)
}

onMounted(async () => {
  observeStageSize()
  await loadState()
  timer = window.setInterval(loadState, 1500)
})

onBeforeUnmount(() => {
  stageResizeObserver?.disconnect()
  stageResizeObserver = null
  if (timer !== null) {
    window.clearInterval(timer)
  }
})

const recentDetections = computed(() => state.value?.recent_detections ?? [])
const edgeStatus = computed(() => state.value?.edge_status ?? [])
const taskLogs = computed(() => state.value?.task_logs ?? [])
const events = computed(() => state.value?.events ?? [])
const analysisResults = computed(() => state.value?.analysis_results ?? [])
const latestDetection = computed(() => recentDetections.value[0] || null)
const serverTime = computed(() => formatTime(state.value?.server_time))
const activeTab = ref<'home' | 'events' | 'settings' | 'logs'>('home')
const onlineEdgeCount = computed(() => edgeStatus.value.filter((item) => item.online).length)
const cloudStatus = computed(() => error.value ? 'DEGRADED' : 'ONLINE')
const pendingEvents = computed(() => events.value.filter((item) => item.status === 'cloud_pending'))
const criticalEvents = computed(() => events.value.filter((item) => item.severity === 'critical'))
const latestEvent = computed(() => events.value[0] || null)
const latestAnalysis = computed(() => analysisResults.value[0] || null)
const analysisByEvent = computed(() => {
  const map = new Map<string, CloudAnalysisResponse>()
  for (const item of analysisResults.value) map.set(item.event_id, item)
  return map
})
const mediaOverlayStyle = computed<Record<string, string>>(() => {
  const sourceWidth = latestDetection.value?.frame_width || 640
  const sourceHeight = latestDetection.value?.frame_height || 360
  const containerWidth = stageSize.value.width
  const containerHeight = stageSize.value.height
  if (sourceWidth <= 0 || sourceHeight <= 0 || containerWidth <= 0 || containerHeight <= 0) {
    return { left: '0', top: '0', width: '100%', height: '100%' }
  }
  const scale = Math.min(containerWidth / sourceWidth, containerHeight / sourceHeight)
  const mediaWidth = sourceWidth * scale
  const mediaHeight = sourceHeight * scale
  return {
    left: `${(containerWidth - mediaWidth) / 2}px`,
    top: `${(containerHeight - mediaHeight) / 2}px`,
    width: `${mediaWidth}px`,
    height: `${mediaHeight}px`,
  }
})

function boxStyle(item: DetectionResult['detections'][number]): Record<string, string> {
  const width = latestDetection.value?.frame_width || 640
  const height = latestDetection.value?.frame_height || 360
  return {
    left: `${Math.min((item.box.x1 / width) * 100, 96)}%`,
    top: `${Math.min((item.box.y1 / height) * 100, 92)}%`,
    width: `${Math.max(((item.box.x2 - item.box.x1) / width) * 100, 4)}%`,
    height: `${Math.max(((item.box.y2 - item.box.y1) / height) * 100, 6)}%`,
  }
}

interface PoseOverlay {
  points: NormalizedKeypoint[]
  edges: SkeletonEdge[]
}

function poseOverlay(item: Detection): PoseOverlay {
  const width = latestDetection.value?.frame_width || 640
  const height = latestDetection.value?.frame_height || 360
  const keypoints = item.keypoints ?? []
  const points = keypoints.map((kpt, index) => normalizeKeypoint(index, kpt, width, height))
  const edges: SkeletonEdge[] = []
  for (const [a, b] of COCO_SKELETON) {
    const ka = keypoints[a]
    const kb = keypoints[b]
    if (!isKeypointVisible(ka) || !isKeypointVisible(kb)) continue
    const na = points[a]
    const nb = points[b]
    edges.push({ x1: na.leftPct, y1: na.topPct, x2: nb.leftPct, y2: nb.topPct })
  }
  return { points: points.filter((p) => isKeypointVisible(keypoints[p.index])), edges }
}

function keypointTitle(p: NormalizedKeypoint): string {
  const name = p.kpt.name ?? `keypoint_${p.index}`
  return `${name} · ${formatNumber(p.kpt.confidence, 2)}`
}

function eventTypeLabel(value: string): string {
  const map: Record<string, string> = {
    person_count: '人数变化',
    pose_raising_hand: '举手',
    pose_head_down: '低头',
    pose_head_left: '头部左偏',
    pose_head_right: '头部右偏',
    pose_upper_body_left: '上身左倾',
    pose_upper_body_right: '上身右倾',
    long_head_down: '长时间低头',
    fall_suspected: '疑似摔倒',
    crowding: '多人聚集',
    pose_uncertain: '姿态不确定',
  }
  return map[value] ?? value
}

function severityLabel(value: string): string {
  const map: Record<string, string> = { info: 'INFO', warning: 'WARN', critical: 'CRITICAL' }
  return map[value] ?? value.toUpperCase()
}

function statusLabel(value: string): string {
  const map: Record<string, string> = {
    edge_resolved: '边端完成',
    cloud_pending: '等待云端',
    cloud_analyzed: '云端已分析',
  }
  return map[value] ?? value
}

function analysisFor(event: SafetyEvent): CloudAnalysisResponse | undefined {
  return analysisByEvent.value.get(event.event_id)
}
</script>

<template>
  <div class="shell">
    <!-- Error bar -->
    <div v-if="error" class="error-bar">{{ error }}</div>

    <!-- Top bar -->
    <header class="topbar">
      <div class="topbar-left">
        <div class="logo">
          <span class="logo-dot"></span>
          <span>Cloud Station</span>
        </div>
        <nav class="tab-group">
          <button class="tab-btn" :class="{ active: activeTab === 'home' }" @click="activeTab = 'home'">监控</button>
          <button class="tab-btn" :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">事件</button>
          <button class="tab-btn" :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">智能体</button>
          <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="activeTab = 'logs'">日志</button>
        </nav>
      </div>
      <div class="topbar-right">
        <div class="status-pill" :class="{ offline: !!error }">
          <span class="pulse"></span>
          {{ cloudStatus }}
        </div>
        <span class="server-time">{{ serverTime }}</span>
      </div>
    </header>

    <!-- Home -->
    <main v-if="activeTab === 'home'" class="main main-home">
      <!-- Detection viewport -->
      <div class="viewport">
        <div ref="stageRef" class="frame-wrap">
          <img
            v-if="latestDetection?.image_jpeg_base64"
            class="frame-image"
            :src="`data:image/jpeg;base64,${latestDetection.image_jpeg_base64}`"
            alt="edge camera frame"
          />
          <div v-else class="frame-placeholder">
            <svg viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            <strong>等待边端快照</strong>
            <span>云端每 1.5 秒刷新状态，画面由边端检测周期压缩后上报。</span>
          </div>

          <!-- HUD overlay -->
          <div v-if="latestDetection" class="frame-hud">
            <span class="hud-tag">#{{ latestDetection.frame_id }}</span>
            <span class="hud-tag">{{ formatNumber(latestDetection.fps) }} FPS</span>
            <span class="hud-tag">{{ formatNumber(latestDetection.inference_ms, 1) }}ms</span>
            <span class="hud-tag">{{ latestDetection.backend || '--' }}</span>
            <span class="hud-tag">{{ formatTime(latestDetection.created_at) }}</span>
          </div>

          <!-- Pose badge -->
          <div v-if="latestDetection?.pose" class="pose-alert" :class="latestDetection.pose.needs_cloud ? 'candidate' : 'stable'">
            <span>{{ latestDetection.pose.action }}</span>
            <span style="opacity:0.6;font-weight:400">{{ latestDetection.pose.needs_cloud ? '需复核' : '稳定' }}</span>
          </div>

          <!-- Detection boxes + pose -->
          <div v-if="latestDetection" class="media-overlay" :style="mediaOverlayStyle">
            <template v-for="(item, idx) in latestDetection.detections" :key="`pose-${idx}`">
              <div class="box" :style="boxStyle(item)">
                <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
              </div>
              <svg class="pose-layer" viewBox="0 0 100 100" preserveAspectRatio="none">
                <line
                  v-for="(edge, ei) in poseOverlay(item).edges"
                  :key="ei"
                  :x1="edge.x1" :y1="edge.y1"
                  :x2="edge.x2" :y2="edge.y2"
                />
              </svg>
              <div
                v-for="p in poseOverlay(item).points"
                :key="`kpt-${idx}-${p.index}`"
                class="kpt"
                :class="{ dim: p.dim }"
                :style="{ left: `${p.leftPct}%`, top: `${p.topPct}%` }"
                :title="keypointTitle(p)"
              ></div>
            </template>
          </div>
        </div>

        <!-- Bottom: detection table -->
        <div class="bottom-bar">
          <div class="det-table-wrap">
            <div class="det-table-title">最近检测结果</div>
            <table v-if="latestDetection?.detections?.length" class="det-table">
              <thead>
                <tr><th>Label</th><th>Conf</th><th>Box</th></tr>
              </thead>
              <tbody>
                <tr v-for="item in latestDetection.detections" :key="`${item.label}-${item.confidence}`">
                  <td class="label-cell">{{ item.label }}</td>
                  <td>{{ formatNumber(item.confidence, 2) }}</td>
                  <td>{{ item.box.x1.toFixed(0) }}, {{ item.box.y1.toFixed(0) }}, {{ item.box.x2.toFixed(0) }}, {{ item.box.y2.toFixed(0) }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="latestDetection?.model_path" class="model-path">{{ latestDetection.model_path }}</div>
            <div v-if="!latestDetection?.detections?.length" class="no-data">暂无检测结果</div>
          </div>
        </div>
      </div>

      <!-- Right sidebar -->
      <aside class="sidebar">
        <!-- Metrics -->
        <div class="sidebar-section">
          <div class="sidebar-section-title">实时指标</div>
          <div class="metric-grid">
            <div class="metric-card">
              <div class="metric-label">检测目标</div>
              <div class="metric-value">{{ latestDetection ? latestDetection.detections.length : 0 }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">推理耗时</div>
              <div class="metric-value small">{{ latestDetection ? `${formatNumber(latestDetection.inference_ms, 1)}ms` : '--' }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">事件</div>
              <div class="metric-value">{{ events.length }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">待分析</div>
              <div class="metric-value">{{ pendingEvents.length }}</div>
            </div>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="sidebar-section-title">边云调度</div>
          <div class="event-mini-grid">
            <div class="flow-cell edge">
              <span>EDGE</span>
              <strong>{{ events.filter((item) => item.status === 'edge_resolved').length }}</strong>
            </div>
            <div class="flow-cell cloud">
              <span>CLOUD</span>
              <strong>{{ analysisResults.length }}</strong>
            </div>
          </div>
          <div v-if="latestAnalysis" class="analysis-brief">
            <span class="risk-chip" :class="latestAnalysis.risk_level">{{ severityLabel(latestAnalysis.risk_level) }}</span>
            <p>{{ latestAnalysis.conclusion }}</p>
          </div>
          <div v-else class="no-data">暂无云端分析结果</div>
        </div>

        <!-- Model info -->
        <div class="sidebar-section">
          <div class="sidebar-section-title">模型信息</div>
          <div class="metric-grid">
            <div class="metric-card" style="grid-column:1/-1">
              <div class="metric-label">任务</div>
              <div class="metric-value small">{{ latestDetection?.model_task || '--' }}</div>
            </div>
            <div class="metric-card" style="grid-column:1/-1">
              <div class="metric-label">设备</div>
              <div class="metric-value small">{{ latestDetection?.device_id || deviceId }}</div>
            </div>
          </div>
        </div>

        <!-- Edge devices -->
        <div class="sidebar-section">
          <div class="sidebar-section-title">边端设备 · {{ onlineEdgeCount }} 在线</div>
          <div v-if="edgeStatus.length" class="device-list">
            <div v-for="device in edgeStatus" :key="device.device_id" class="device-item">
              <span class="device-name">{{ device.device_id }}</span>
              <span class="device-status" :class="device.online ? 'on' : 'off'">{{ device.online ? 'ON' : 'OFF' }}</span>
              <div class="device-stats">
                <span>FPS {{ formatNumber(device.fps) }}</span>
                <span>CPU {{ formatNumber(device.cpu_percent) }}%</span>
                <span>MEM {{ formatNumber(device.memory_percent) }}%</span>
              </div>
              <div class="device-meta">{{ device.network }} · {{ formatTime(device.last_seen) }}</div>
            </div>
          </div>
          <div v-else class="no-data">暂无边端在线</div>
        </div>

        <div class="sidebar-section">
          <div class="sidebar-section-title">最近事件</div>
          <div v-if="latestEvent" class="event-card compact" :class="latestEvent.severity">
            <div class="event-head">
              <strong>{{ eventTypeLabel(latestEvent.event_type) }}</strong>
              <span class="status-chip" :class="latestEvent.status">{{ statusLabel(latestEvent.status) }}</span>
            </div>
            <p>{{ latestEvent.summary }}</p>
            <div class="event-meta">{{ latestEvent.device_id }} · {{ formatTime(latestEvent.created_at) }}</div>
          </div>
          <div v-else class="no-data">暂无边端事件</div>
        </div>
      </aside>
    </main>

    <!-- Events -->
    <main v-else-if="activeTab === 'events'" class="main main-events">
      <section class="events-board">
        <div class="events-summary">
          <div class="summary-tile">
            <span>总事件</span>
            <strong>{{ events.length }}</strong>
          </div>
          <div class="summary-tile warning">
            <span>待云端</span>
            <strong>{{ pendingEvents.length }}</strong>
          </div>
          <div class="summary-tile critical">
            <span>高风险</span>
            <strong>{{ criticalEvents.length }}</strong>
          </div>
          <div class="summary-tile">
            <span>分析报告</span>
            <strong>{{ analysisResults.length }}</strong>
          </div>
        </div>

        <div class="events-layout">
          <div class="event-list-panel">
            <div class="panel-title">异常事件与边云分工</div>
            <div v-if="events.length" class="event-list">
              <article v-for="event in events" :key="event.event_id" class="event-card" :class="event.severity">
                <div class="event-head">
                  <div>
                    <strong>{{ eventTypeLabel(event.event_type) }}</strong>
                    <div class="event-meta">{{ event.device_id }} · {{ formatTime(event.created_at) }}</div>
                  </div>
                  <div class="chip-row">
                    <span class="risk-chip" :class="event.severity">{{ severityLabel(event.severity) }}</span>
                    <span class="status-chip" :class="event.status">{{ statusLabel(event.status) }}</span>
                  </div>
                </div>
                <p>{{ event.summary }}</p>
                <div v-if="event.evidence.length" class="evidence-line">{{ event.evidence.slice(0, 2).join(' / ') }}</div>
                <div v-if="analysisFor(event)" class="event-analysis-link">
                  {{ analysisFor(event)?.conclusion }}
                </div>
                <div class="event-actions">
                  <button class="mini-btn" type="button" @click="openReport(event)">查看报告</button>
                </div>
              </article>
            </div>
            <div v-else class="empty-state">暂无事件。边端生成的本地事件和云端候选会显示在这里。</div>
          </div>

          <div class="analysis-panel">
            <div class="panel-title">云端 Agent 分析</div>
            <div v-if="reportError" class="report-error">{{ reportError }}</div>
            <article v-if="selectedReport" class="report-panel">
              <div class="event-head">
                <div>
                  <strong>事件报告</strong>
                  <div class="event-meta">{{ selectedReport.event.event_id }} · {{ formatTime(selectedReport.created_at) }}</div>
                </div>
                <button class="mini-btn primary" type="button" @click="exportReport(selectedReport)">导出 Markdown</button>
              </div>
              <pre>{{ selectedReport.report_markdown }}</pre>
            </article>
            <div v-if="analysisResults.length" class="analysis-list">
              <article v-for="item in analysisResults" :key="item.event_id" class="analysis-card" :class="item.risk_level">
                <div class="event-head">
                  <strong>{{ item.conclusion }}</strong>
                  <span class="risk-chip" :class="item.risk_level">{{ severityLabel(item.risk_level) }}</span>
                </div>
                <div class="analysis-section">
                  <span>判断依据</span>
                  <p>{{ item.reasoning.slice(0, 3).join('；') || '--' }}</p>
                </div>
                <div class="analysis-section">
                  <span>处置建议</span>
                  <p>{{ item.suggestions.slice(0, 3).join('；') || '--' }}</p>
                </div>
                <div class="event-meta">知识库 {{ item.used_knowledge ? 'YES' : 'NO' }} · 搜索 {{ item.used_search ? 'YES' : 'NO' }} · {{ formatTime(item.created_at) }}</div>
              </article>
            </div>
            <div v-else class="empty-state">云端分析报告会显示在这里。</div>
          </div>
        </div>
      </section>
    </main>

    <!-- Settings -->
    <main v-else-if="activeTab === 'settings'" class="main main-settings">
      <div class="settings-page">
        <div class="settings-form">
          <div class="field">
            <label class="field-label">设备 ID</label>
            <input class="field-input" v-model="deviceId" type="text" />
          </div>
          <div class="field">
            <label class="field-label">问题</label>
            <textarea class="field-textarea" v-model="chatQuestion" rows="5"></textarea>
          </div>
          <button class="btn btn-primary" type="button" @click="submitChat">发送到云端智能体</button>
          <div style="height:1px;background:var(--border);margin:4px 0"></div>
          <div class="field">
            <label class="field-label">任务描述</label>
            <input class="field-input" v-model="taskText" type="text" />
          </div>
          <button class="btn btn-secondary" type="button" @click="submitSchedule">预测调度位置</button>
        </div>

        <div class="settings-results">
          <div v-if="chatResult" class="result-block">
            <div class="result-tag">智能体回复</div>
            <div class="result-body">{{ chatResult.answer }}</div>
            <ul v-if="chatResult.traces?.length" class="trace-list">
              <li v-for="trace in chatResult.traces" :key="trace">{{ trace }}</li>
            </ul>
          </div>
          <div v-else class="empty-state">智能体回复会显示在这里</div>

          <div v-if="scheduleResult" class="result-block">
            <div class="result-tag">调度决策</div>
            <div class="result-title">{{ scheduleResult.target }} / {{ scheduleResult.complexity }}</div>
            <div class="result-body">{{ scheduleResult.reason }}</div>
          </div>
        </div>
      </div>
    </main>

    <!-- Logs -->
    <main v-else class="main main-logs">
      <div class="logs-page">
        <div class="logs-header">
          <h2 class="logs-title">任务日志</h2>
          <span class="logs-count">{{ taskLogs.length }} records</span>
        </div>
        <div v-if="taskLogs.length" class="log-list">
          <div v-for="log in taskLogs" :key="log.task_id" class="log-item">
            <div>
              <div class="log-task">{{ log.task }}</div>
              <div class="log-summary">{{ log.result_summary }}</div>
              <div class="device-meta" style="margin-top:6px">{{ log.device_id }} · {{ formatTime(log.created_at) }}</div>
            </div>
            <span class="log-target">{{ log.target }}</span>
          </div>
        </div>
        <div v-else class="empty-state">暂无任务日志</div>
      </div>
    </main>
  </div>
</template>
