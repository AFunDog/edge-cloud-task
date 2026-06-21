<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref } from 'vue'
import { connectStream, connectWebRTC, fetchState } from './api'
import type {
  CloudAnalysisResponse,
  Detection,
  DetectionResult,
  EdgeStatus,
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
const connected = ref(false)
const rtcConnected = ref(false)
const videoWidth = ref(640)
const videoHeight = ref(360)
const deviceId = ref('edge-camera-01')

let streamControl: { close: () => void } | null = null
let rtcControl: { close: () => void } | null = null
let rtcReconnectTimer: number | null = null
let rtcConnecting = false
let stopped = false
const videoRef = ref<HTMLVideoElement | null>(null)
const frameRef = ref<HTMLElement | null>(null)
const frameSize = ref({ width: 0, height: 0 })
let frameResizeObserver: ResizeObserver | null = null

// ---------- 回调 ----------

function applySnapshot(snapshot: SystemState): void {
  state.value = snapshot
  loading.value = false
  error.value = ''
}

function applyDetection(detection: DetectionResult): void {
  if (!state.value) {
    state.value = {
      server_time: detection.created_at,
      edge_status: [],
      recent_detections: [detection],
      task_logs: [],
      events: [],
      analysis_results: [],
    }
    loading.value = false
    return
  }
  state.value = {
    ...state.value,
    server_time: detection.created_at,
    recent_detections: [detection, ...state.value.recent_detections.slice(0, 49)],
  }
}

function applyEdgeStatus(status: EdgeStatus): void {
  if (!state.value) return
  const others = state.value.edge_status.filter((s) => s.device_id !== status.device_id)
  state.value = { ...state.value, edge_status: [status, ...others] }
}

function applyTaskLog(log: TaskLog): void {
  if (!state.value) return
  state.value = { ...state.value, task_logs: [log, ...state.value.task_logs.slice(0, 199)] }
}

function applyEvent(event: SafetyEvent): void {
  if (!state.value) return
  state.value = { ...state.value, events: [event, ...state.value.events.slice(0, 199)] }
}

function applyAnalysisResult(result: CloudAnalysisResponse): void {
  if (!state.value) return
  state.value = {
    ...state.value,
    analysis_results: [result, ...state.value.analysis_results.slice(0, 199)],
    events: state.value.events.map((event) =>
      event.event_id === result.event_id ? { ...event, status: 'cloud_analyzed' } : event,
    ),
  }
}

function updateFrameSize(): void {
  if (!frameRef.value) return
  const rect = frameRef.value.getBoundingClientRect()
  frameSize.value = { width: rect.width, height: rect.height }
}

function observeFrameSize(): void {
  updateFrameSize()
  if (!frameRef.value) return
  frameResizeObserver = new ResizeObserver(updateFrameSize)
  frameResizeObserver.observe(frameRef.value)
}

// ---------- 初始化 ----------

async function loadInitialState(): Promise<void> {
  try {
    error.value = ''
    state.value = await fetchState()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    loading.value = false
  }
}

function openStream(): void {
  streamControl = connectStream({
    onSnapshot: applySnapshot,
    onDetection: applyDetection,
    onStatus: applyEdgeStatus,
    onTaskLog: applyTaskLog,
    onEvent: applyEvent,
    onAnalysisResult: applyAnalysisResult,
    onError: (msg) => { error.value = msg },
    onOpen: () => { connected.value = true; loading.value = false },
    onClose: () => { connected.value = false },
  })
}

async function openWebRTC(): Promise<void> {
  if (!videoRef.value || stopped || rtcConnecting) return
  if (rtcConnected.value && videoRef.value.srcObject) {
    await videoRef.value.play().catch(() => {})
    return
  }
  rtcConnecting = true
  rtcControl?.close()
  rtcControl = null
  try {
    rtcControl = await connectWebRTC(
      videoRef.value,
      (w, h) => { videoWidth.value = w; videoHeight.value = h },
      (isConnected) => {
        rtcConnected.value = isConnected
        if (!isConnected && !rtcConnecting) {
          rtcControl = null
          scheduleRtcReconnect()
        }
      },
    )
  } catch (exc) {
    console.error('[RTC] 连接失败', exc)
    rtcConnected.value = false
  } finally {
    rtcConnecting = false
    if (!rtcControl) scheduleRtcReconnect()
  }
}

function scheduleRtcReconnect(): void {
  if (stopped || rtcReconnectTimer !== null) return
  rtcReconnectTimer = window.setTimeout(() => {
    rtcReconnectTimer = null
    void openWebRTC()
  }, 1500)
}

async function activateMonitor(): Promise<void> {
  if (!frameResizeObserver && frameRef.value) observeFrameSize()
  updateFrameSize()
  await openWebRTC()
}

onMounted(() => {
  stopped = false
  observeFrameSize()
  openStream()
  void openWebRTC()
  void loadInitialState()
})

onBeforeUnmount(() => {
  stopped = true
  frameResizeObserver?.disconnect()
  frameResizeObserver = null
  if (rtcReconnectTimer !== null) window.clearTimeout(rtcReconnectTimer)
  streamControl?.close()
  streamControl = null
  rtcControl?.close()
  rtcControl = null
})

// ---------- 计算属性 ----------

const edgeStatus = computed(() => state.value?.edge_status[0] ?? null)
const latestDetection = computed(() => state.value?.recent_detections[0] ?? null)
const taskLogs = computed(() => state.value?.task_logs ?? [])
const events = computed(() => state.value?.events ?? [])
const analysisResults = computed(() => state.value?.analysis_results ?? [])
const latestAnalysis = computed(() => analysisResults.value[0] ?? null)
const pendingEvents = computed(() => events.value.filter((event) => event.status === 'cloud_pending'))
const analyzedEvents = computed(() => events.value.filter((event) => event.status === 'cloud_analyzed'))
const hasUnauthorizedTime = computed(() =>
  events.value.some((event) => event.event_type === 'unauthorized_time' && event.status === 'cloud_pending'),
)
const hasExcessivePeople = computed(() =>
  events.value.some((event) => event.event_type === 'excessive_people' && event.status === 'cloud_pending'),
)
const nowTick = ref(Date.now())
setInterval(() => { nowTick.value = Date.now() }, 30000)
const hourNow = computed(() => new Date(nowTick.value).getHours().toString().padStart(2, '0'))
const minuteNow = computed(() => new Date(nowTick.value).getMinutes().toString().padStart(2, '0'))
const pose = computed(() => latestDetection.value?.pose ?? null)
const detections = computed(() => latestDetection.value?.detections ?? [])
const showVideoAnnotations = computed(() => rtcConnected.value && latestDetection.value !== null)
const activeAction = computed(() => pose.value?.action ?? 'unknown')
const cloudHint = computed(() =>
  pose.value?.needs_cloud ? '边端未能稳定匹配，已进入云端复核候选' : '边端规则命中稳定，可在本地完成',
)
const mediaOverlayStyle = computed<Record<string, string>>(() => {
  const sourceWidth = latestDetection.value?.frame_width || videoWidth.value || 640
  const sourceHeight = latestDetection.value?.frame_height || videoHeight.value || 360
  const containerWidth = frameSize.value.width
  const containerHeight = frameSize.value.height
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

function boxStyle(item: Detection, current: DetectionResult | null): Record<string, string> {
  const width = current?.frame_width || videoWidth.value
  const height = current?.frame_height || videoHeight.value
  return {
    left: `${Math.min((item.box.x1 / width) * 100, 96)}%`,
    top: `${Math.min((item.box.y1 / height) * 100, 92)}%`,
    width: `${Math.max(((item.box.x2 - item.box.x1) / width) * 100, 4)}%`,
    height: `${Math.max(((item.box.y2 - item.box.y1) / height) * 100, 6)}%`,
  }
}

function actionLabel(value: string): string {
  const map: Record<string, string> = {
    standing: '上身直立',
    sitting: '坐下',
    raising_hand: '举手',
    crouching: '蹲下',
    head_left: '头部左偏',
    head_right: '头部右偏',
    head_down: '低头',
    upper_body_left: '上身左倾',
    upper_body_right: '上身右倾',
    unknown: '待复核',
  }
  return map[value] ?? value
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

function statusLabel(value: string): string {
  const map: Record<string, string> = {
    edge_resolved: '边端完成',
    cloud_pending: '云端候选',
    cloud_analyzed: '云端已分析',
  }
  return map[value] ?? value
}

function severityLabel(value: string): string {
  const map: Record<string, string> = { info: 'INFO', warning: 'WARN', critical: 'CRITICAL' }
  return map[value] ?? value.toUpperCase()
}

// ---------- 姿态关键点与骨架渲染辅助 ----------

interface PoseOverlay {
  points: NormalizedKeypoint[]
  edges: SkeletonEdge[]
}

/** 将单个检测的关键点归一化为容器内百分比，并计算可见骨架边。 */
function poseOverlay(item: Detection, current: DetectionResult | null): PoseOverlay {
  const width = current?.frame_width || videoWidth.value
  const height = current?.frame_height || videoHeight.value
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



provide('edgeStation', {
  state, loading, error, connected, rtcConnected, videoWidth, videoHeight, deviceId, videoRef, frameRef, frameSize,
  edgeStatus, latestDetection, taskLogs, events, analysisResults, latestAnalysis, pendingEvents, analyzedEvents,
  hasUnauthorizedTime, hasExcessivePeople, hourNow, minuteNow, pose, detections, showVideoAnnotations, activeAction,
  cloudHint, mediaOverlayStyle, boxStyle, actionLabel, eventTypeLabel, statusLabel, severityLabel, poseOverlay, keypointTitle,
  updateFrameSize, openWebRTC, activateMonitor, formatNumber, formatTime,
})
</script>

<template>
  <div class="shell">
    <div v-if="error" class="error-bar">{{ error }}</div>

    <header class="topbar">
      <div class="topbar-left">
        <div class="logo">
          <span class="logo-dot"></span>
          <span>Edge Station</span>
        </div>
        <nav class="tab-group">
          <RouterLink class="tab-btn" to="/">监控</RouterLink>
          <RouterLink class="tab-btn" to="/pose">姿态</RouterLink>
          <RouterLink class="tab-btn" to="/logs">日志</RouterLink>
        </nav>
      </div>
      <div class="topbar-right">
        <div class="status-pill" :class="{ offline: !rtcConnected }">
          <span class="pulse"></span>
          {{ rtcConnected ? 'WEBRTC' : (connected ? 'WS' : 'OFFLINE') }}
        </div>
        <span class="server-time">{{ formatTime(state?.server_time) }}</span>
      </div>
    </header>

    <RouterView v-slot="{ Component }">
      <KeepAlive include="MonitorView">
        <component :is="Component" />
      </KeepAlive>
    </RouterView>
  </div>
</template>
