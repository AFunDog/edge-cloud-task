<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { connectStream, connectWebRTC, fetchState } from './api'
import type { Detection, DetectionResult, EdgeStatus, SystemState, TaskLog } from './types'
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
    onError: (msg) => { error.value = msg },
    onOpen: () => { connected.value = true; loading.value = false },
    onClose: () => { connected.value = false },
  })
}

async function openWebRTC(): Promise<void> {
  if (!videoRef.value || stopped || rtcConnecting) return
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
          <button class="tab-btn active" type="button">监控</button>
          <button class="tab-btn" type="button">姿态</button>
          <button class="tab-btn" type="button">日志</button>
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

    <main class="main main-home">
      <section class="viewport">
        <div ref="frameRef" class="frame-wrap">
          <video
            ref="videoRef"
            class="frame-video"
            autoplay
            playsinline
            muted
          ></video>
          <div v-if="!rtcConnected" class="frame-placeholder">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
            <strong>等待边端摄像头画面</strong>
            <span>正在建立 WebRTC 视频连接；检测数据与视频使用不同通道。</span>
          </div>

          <div v-if="showVideoAnnotations && latestDetection" class="frame-hud">
            <span class="hud-tag">#{{ latestDetection.frame_id }}</span>
            <span class="hud-tag">{{ formatNumber(latestDetection.fps) }} FPS</span>
            <span class="hud-tag">{{ formatNumber(latestDetection.inference_ms, 1) }}ms</span>
            <span class="hud-tag">{{ latestDetection.backend || '--' }}</span>
            <span class="hud-tag">{{ latestDetection.model_task || '--' }}</span>
          </div>

          <div class="pose-alert" :class="pose?.needs_cloud ? 'candidate' : 'stable'">
            <span>{{ actionLabel(activeAction) }}</span>
            <span style="opacity:0.62;font-weight:400">
              {{ pose?.confidence ? `置信度 ${formatNumber(pose.confidence, 2)}` : '等待有效姿态' }}
            </span>
          </div>

          <div v-if="showVideoAnnotations && latestDetection" class="cloud-hint">
            <span>{{ cloudHint }}</span>
          </div>

          <div v-if="showVideoAnnotations && latestDetection" class="media-overlay" :style="mediaOverlayStyle">
            <template v-for="(item, idx) in detections" :key="`target-${idx}`">
              <div class="box" :style="boxStyle(item, latestDetection)">
                <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
              </div>

              <!-- 姿态骨架（连线） -->
              <svg class="pose-layer" viewBox="0 0 100 100" preserveAspectRatio="none">
                <line
                  v-for="(edge, ei) in poseOverlay(item, latestDetection).edges"
                  :key="ei"
                  :x1="edge.x1"
                  :y1="edge.y1"
                  :x2="edge.x2"
                  :y2="edge.y2"
                />
              </svg>

              <!-- 姿态关键点（圆点） -->
              <div
                v-for="p in poseOverlay(item, latestDetection).points"
                :key="`kpt-${idx}-${p.index}`"
                class="kpt"
                :class="{ dim: p.dim }"
                :style="{ left: `${p.leftPct}%`, top: `${p.topPct}%` }"
                :title="keypointTitle(p)"
              ></div>
            </template>
          </div>
        </div>

        <div class="bottom-bar">
          <div class="det-table-wrap">
            <div class="det-table-title">最近检测结果</div>
            <table v-if="detections.length" class="det-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Conf</th>
                  <th>Box</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in detections" :key="`${item.label}-${item.confidence}`">
                  <td class="label-cell">{{ item.label }}</td>
                  <td>{{ formatNumber(item.confidence, 2) }}</td>
                  <td>
                    {{ item.box.x1.toFixed(0) }}, {{ item.box.y1.toFixed(0) }},
                    {{ item.box.x2.toFixed(0) }}, {{ item.box.y2.toFixed(0) }}
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="latestDetection?.model_path" class="model-path">{{ latestDetection.model_path }}</div>
            <div v-if="!detections.length" class="no-data">暂无检测结果</div>
          </div>
        </div>
      </section>

      <aside class="sidebar">
        <section class="sidebar-section">
          <div class="sidebar-section-title">实时指标</div>
          <div class="metric-grid">
            <div class="metric-card">
              <div class="metric-label">检测目标</div>
              <div class="metric-value">{{ detections.length }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">推理耗时</div>
              <div class="metric-value small">{{ latestDetection ? `${formatNumber(latestDetection.inference_ms, 1)}ms` : '--' }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">姿态</div>
              <div class="metric-value small">{{ actionLabel(activeAction) }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">云端候选</div>
              <div class="metric-value small">{{ pose?.needs_cloud ? 'YES' : 'NO' }}</div>
            </div>
          </div>
        </section>

        <section class="sidebar-section">
          <div class="sidebar-section-title">边端设备</div>
          <div class="device-list">
            <div class="device-item">
              <span class="device-name">{{ edgeStatus?.device_id ?? deviceId }}</span>
              <span class="device-status" :class="edgeStatus?.online ? 'on' : 'off'">
                {{ edgeStatus?.online ? 'ON' : 'OFF' }}
              </span>
              <div class="device-stats">
                <span>FPS {{ formatNumber(edgeStatus?.fps ?? 0) }}</span>
                <span>CPU {{ formatNumber(edgeStatus?.cpu_percent ?? 0) }}%</span>
                <span>MEM {{ formatNumber(edgeStatus?.memory_percent ?? 0) }}%</span>
              </div>
              <div class="device-meta">
                {{ edgeStatus?.network ?? 'unknown' }} · {{ edgeStatus ? formatTime(edgeStatus.last_seen) : '--' }}
              </div>
            </div>
          </div>
        </section>

        <section class="sidebar-section logs-section">
          <div class="sidebar-section-title">边端日志</div>
          <div v-if="error" class="notice error">{{ error }}</div>
          <div v-else-if="loading" class="notice">正在拉取边端状态...</div>
          <div v-if="taskLogs.length" class="log-list">
            <div v-for="log in taskLogs.slice(0, 12)" :key="log.task_id" class="log-item">
              <div>
                <div class="log-task">{{ log.task }}</div>
                <div class="log-summary">{{ log.result_summary }}</div>
                <div class="device-meta" style="margin-top:6px">{{ log.device_id }} · {{ formatTime(log.created_at) }}</div>
              </div>
              <span class="log-target">{{ log.target }}</span>
            </div>
          </div>
          <div v-else class="no-data">边端日志会在这里实时汇总</div>
        </section>
      </aside>
    </main>
  </div>
</template>
