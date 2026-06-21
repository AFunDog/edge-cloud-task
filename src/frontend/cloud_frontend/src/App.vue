<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref } from 'vue'
import { connectStream, connectWebRTC, fetchChatHistory, fetchDailyReport, fetchEventReport, fetchKnowledgeFile, fetchKnowledgeFiles, fetchState, getDailyReportHtmlUrl, getDailyReportMdUrl, saveKnowledgeFile, scanHazards, scheduleTask, sendAgentChat } from './api'
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
import { renderMarkdown } from './utils/markdown'

const state = ref<SystemState | null>(null)
const loading = ref(true)
const error = ref('')
const chatQuestion = ref('请分析当前边缘端画面是否存在异常，并给出调度建议。')
const deviceId = ref('edge-camera-01')
const taskText = ref('姿态识别')
const chatResult = ref<any>(null)
const chatLoading = ref(false)
const chatHistory = ref<any[]>([])
const chatHistoryLoaded = ref(false)
const kbFiles = ref<Array<{ name: string; size: number }>>([])
const kbActiveFile = ref('')
const kbContent = ref('')
const kbLoading = ref(false)
const kbSaving = ref(false)
const kbSaved = ref(false)
const videoRef = ref<HTMLVideoElement | null>(null)
const streamConnected = ref(false)
const liveDetection = ref<DetectionResult | null>(null)
const rtcConnected = ref(false)
const rtcConnecting = ref(false)
let streamControl: { close: () => void } | null = null
let rtcControl: { close: () => void } | null = null
let rtcReconnectTimer: number | null = null
const scheduleResult = ref<any>(null)
const scanResult = ref<any>(null)
const scanning = ref(false)
const dailyReport = ref<any>(null)
const dailyLoading = ref(false)
const dailyReportMdUrl = ref('')
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
    chatLoading.value = true
    chatResult.value = null
    chatResult.value = await sendAgentChat({
      question: chatQuestion.value,
      device_id: deviceId.value,
      context: { source: 'web-console' },
    })
    await loadChatHistory()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    chatLoading.value = false
  }
}

function downloadReportMd(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function buildChatReportMd(item: any): string {
  const lines = [
    `# 智能体对话报告`,
    `- 时间: ${formatTime(item.created_at)}`,
    `- 设备: ${item.device_id}`,
    `- 知识库: ${item.used_knowledge ? 'YES' : 'NO'} · 搜索: ${item.used_search ? 'YES' : 'NO'}`,
    ``,
    `## 问题`,
    item.question,
    ``,
    `## 回复`,
    item.answer,
  ]
  if (item.traces?.length) {
    lines.push('', '## 执行追踪', ...item.traces.map((t: string) => `- ${t}`))
  }
  if (item.context && Object.keys(item.context).length) {
    lines.push('', '## 场景上下文', '```json', JSON.stringify(item.context, null, 2), '```')
  }
  return lines.join('\n')
}

function printChatReport(item: any): void {
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>智能体对话报告</title>
<style>body{font-family:sans-serif;max-width:800px;margin:40px auto;line-height:1.7;color:#222}
h1{font-size:20px}h2{font-size:16px;margin-top:20px}pre{background:#f5f5f5;padding:12px;border-radius:6px;font-size:12px}
.timestamp{color:#888;font-size:13px}.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;margin-right:6px}
</style></head><body>
<h1>智能体对话报告</h1>
<p class="timestamp">时间: ${formatTime(item.created_at)} | 设备: ${item.device_id}</p>
<p>知识库: ${item.used_knowledge ? 'YES' : 'NO'} · 搜索: ${item.used_search ? 'YES' : 'NO'}</p>
<h2>问题</h2><p>${item.question}</p>
<h2>回复</h2>${renderMarkdown(item.answer)}
${item.context && Object.keys(item.context).length ? `<h2>场景上下文</h2><pre>${JSON.stringify(item.context, null, 2)}</pre>` : ''}
</body></html>`
  const w = window.open('', '_blank')
  if (w) { w.document.write(html); w.document.close(); setTimeout(() => w.print(), 500) }
}

async function loadChatHistory(): Promise<void> {
  try {
    chatHistory.value = await fetchChatHistory()
    chatHistoryLoaded.value = true
  } catch {
    chatHistoryLoaded.value = false
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

async function loadKnowledgeFiles(): Promise<void> {
  try {
    kbFiles.value = await fetchKnowledgeFiles()
  } catch {
    kbFiles.value = []
  }
}

async function openKnowledgeFile(name: string): Promise<void> {
  try {
    kbLoading.value = true
    kbSaved.value = false
    const file = await fetchKnowledgeFile(name)
    kbActiveFile.value = name
    kbContent.value = file.content
  } catch {
    // ignore
  } finally {
    kbLoading.value = false
  }
}

async function submitKnowledgeSave(): Promise<void> {
  if (!kbActiveFile.value) return
  try {
    kbSaving.value = true
    kbSaved.value = false
    await saveKnowledgeFile(kbActiveFile.value, kbContent.value)
    kbSaved.value = true
  } catch {
    // ignore
  } finally {
    kbSaving.value = false
  }
}

function printDailyReport(): void {
  const url = getDailyReportHtmlUrl()
  const w = window.open(url, '_blank')
  if (w) { w.addEventListener('load', () => setTimeout(() => w.print(), 500)) }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function quickQuery(question: string): void {
  chatQuestion.value = question
  submitChat()
}

async function submitScan(): Promise<void> {
  try {
    error.value = ''
    scanning.value = true
    scanResult.value = await scanHazards()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    scanning.value = false
  }
}

async function openDailyReport(): Promise<void> {
  try {
    error.value = ''
    dailyLoading.value = true
    dailyReport.value = await fetchDailyReport()
    dailyReportMdUrl.value = getDailyReportMdUrl()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    dailyLoading.value = false
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

// ---------- WebRTC 视频 ----------

function openStream(): void {
  streamControl?.close()
  streamControl = connectStream({
    onSnapshot: (snapshot) => {
      liveDetection.value = snapshot.recent_detections[0] ?? liveDetection.value
    },
    onDetection: (detection) => {
      liveDetection.value = detection
    },
    onOpen: () => {
      streamConnected.value = true
    },
    onClose: () => {
      streamConnected.value = false
    },
  })
}

async function openWebRTC(): Promise<void> {
  if (!videoRef.value || rtcConnecting.value) return
  if (rtcConnected.value && videoRef.value.srcObject) {
    await videoRef.value.play().catch(() => {})
    return
  }
  rtcConnecting.value = true
  rtcControl?.close()
  rtcControl = null
  try {
    rtcControl = await connectWebRTC(
      videoRef.value,
      undefined,
      (isConnected) => {
        rtcConnected.value = isConnected
        if (!isConnected && !rtcConnecting.value) scheduleRtcReconnect()
      },
    )
  } catch {
    // ignore
  } finally {
    rtcConnecting.value = false
    if (!rtcConnected.value) scheduleRtcReconnect()
  }
}

function scheduleRtcReconnect(): void {
  if (rtcReconnectTimer !== null) return
  rtcReconnectTimer = window.setTimeout(() => {
    rtcReconnectTimer = null
    if (!rtcConnected.value && !rtcConnecting.value) openWebRTC()
  }, 3000)
}

async function activateMonitor(): Promise<void> {
  if (!stageResizeObserver && stageRef.value) observeStageSize()
  updateStageSize()
  await openWebRTC()
}

onMounted(async () => {
  observeStageSize()
  openStream()
  await loadState()
  await loadChatHistory()
  await openWebRTC()
  timer = window.setInterval(loadState, 500)
})

onBeforeUnmount(() => {
  stageResizeObserver?.disconnect()
  stageResizeObserver = null
  if (timer !== null) {
    window.clearInterval(timer)
  }
  if (rtcReconnectTimer !== null) {
    window.clearTimeout(rtcReconnectTimer)
  }
  streamControl?.close()
  streamControl = null
  rtcControl?.close()
})

const recentDetections = computed(() => state.value?.recent_detections ?? [])
const edgeStatus = computed(() => state.value?.edge_status ?? [])
const taskLogs = computed(() => state.value?.task_logs ?? [])
const events = computed(() => state.value?.events ?? [])
const analysisResults = computed(() => state.value?.analysis_results ?? [])
const latestDetection = computed(() => {
  const cloudDetection = recentDetections.value[0] || null
  if (!liveDetection.value) return cloudDetection
  if (!cloudDetection) return liveDetection.value
  return detectionTimestamp(liveDetection.value) >= detectionTimestamp(cloudDetection)
    ? liveDetection.value
    : cloudDetection
})
const serverTime = computed(() => formatTime(state.value?.server_time))
const onlineEdgeCount = computed(() => edgeStatus.value.filter((item) => item.online).length)
const pendingEvents = computed(() => events.value.filter((item) => item.status === 'cloud_pending'))
const criticalEvents = computed(() => events.value.filter((item) => item.severity === 'critical'))
const latestEvent = computed(() => events.value[0] || null)
const latestAnalysis = computed(() => analysisResults.value[0] || null)
const analysisByEvent = computed(() => {
  const map = new Map<string, CloudAnalysisResponse>()
  for (const item of analysisResults.value) map.set(item.event_id, item)
  return map
})
const _sourceSize = computed(() => {
  const fw = latestDetection.value?.frame_width
  const fh = latestDetection.value?.frame_height
  if (fw && fh && fw > 0 && fh > 0) return { width: fw, height: fh }
  return { width: 640, height: 360 }
})

function detectionTimestamp(detection: DetectionResult): number {
  const timestamp = Date.parse(detection.created_at)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const mediaOverlayStyle = computed<Record<string, string>>(() => {
  const { width: sourceWidth, height: sourceHeight } = _sourceSize.value
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
  const { width, height } = _sourceSize.value
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
  const { width, height } = _sourceSize.value
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
    unauthorized_time: '非授权时段',
    excessive_people: '人数超限',
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


provide('cloudStation', {
  state, loading, error, chatQuestion, deviceId, taskText, chatResult, chatLoading, chatHistory, chatHistoryLoaded,
  kbFiles, kbActiveFile, kbContent, kbLoading, kbSaving, kbSaved, videoRef, streamConnected, liveDetection,
  rtcConnected, scheduleResult, scanResult, scanning, dailyReport, dailyLoading, dailyReportMdUrl, selectedReport,
  reportError, stageRef, stageSize, loadState, submitChat, loadChatHistory, submitSchedule, loadKnowledgeFiles,
  openKnowledgeFile, submitKnowledgeSave, formatFileSize, quickQuery, submitScan, openDailyReport, openReport,
  exportReport, downloadReportMd, buildChatReportMd, printChatReport, printDailyReport, updateStageSize, activateMonitor,
  recentDetections, edgeStatus, taskLogs, events, analysisResults,
  latestDetection, serverTime, onlineEdgeCount, pendingEvents, criticalEvents, latestEvent, latestAnalysis, analysisByEvent,
  mediaOverlayStyle, boxStyle, poseOverlay, keypointTitle, eventTypeLabel, severityLabel, statusLabel, analysisFor,
  formatNumber, formatTime, renderMarkdown,
})
</script>

<template>
  <div class="shell">
    <div v-if="error" class="error-bar">{{ error }}</div>

    <header class="topbar">
      <div class="topbar-left">
        <div class="logo">
          <span class="logo-dot"></span>
          <span>Cloud Station</span>
        </div>
        <nav class="tab-group">
          <RouterLink class="tab-btn" to="/">监控</RouterLink>
          <RouterLink class="tab-btn" to="/events">事件</RouterLink>
          <RouterLink class="tab-btn" to="/agent">智能体</RouterLink>
          <RouterLink class="tab-btn" to="/logs">日志</RouterLink>
          <RouterLink class="tab-btn" to="/knowledge">知识库</RouterLink>
        </nav>
      </div>
      <div class="topbar-right">
        <div class="status-pill" :class="{ offline: !rtcConnected && !streamConnected }">
          <span class="pulse"></span>
          {{ rtcConnected ? (streamConnected ? 'WEBRTC + WS' : 'WEBRTC') : (streamConnected ? 'EDGE WS' : (state ? 'DATA' : 'OFFLINE')) }}
        </div>
        <span class="server-time">{{ serverTime }}</span>
      </div>
    </header>

    <RouterView v-slot="{ Component }">
      <KeepAlive include="MonitorView">
        <component :is="Component" />
      </KeepAlive>
    </RouterView>
  </div>
</template>
