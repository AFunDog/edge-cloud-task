<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { connectStream, connectWebRTC, fetchState, scheduleTask } from './api'
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
const taskText = ref('姿态识别')
const deviceId = ref('edge-camera-01')
const scheduleBusy = ref(false)
const scheduleResult = ref<{
  target: string
  complexity: string
  reason: string
} | null>(null)

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
    standing: '站立', sitting: '坐下', raising_hand: '举手', crouching: '蹲下', unknown: '待复核',
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

function latestLog(logs: TaskLog[]): TaskLog | null {
  return logs[0] ?? null
}

async function submitSchedule(): Promise<void> {
  try {
    scheduleBusy.value = true
    error.value = ''
    scheduleResult.value = await scheduleTask({
      task: taskText.value,
      device_id: deviceId.value,
      context: { source: 'edge-workbench' },
    })
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    scheduleBusy.value = false
  }
}
</script>

<template>
  <div class="shell">
    <div class="mesh mesh-a"></div>
    <div class="mesh mesh-b"></div>
    <div class="mesh mesh-c"></div>

    <header class="masthead">
      <div class="masthead-copy">
        <p class="eyebrow">Edge Station</p>
        <h1>边端姿态工作台</h1>
        <p class="lede">
          边端优先完成摄像头采集、YOLO 检测和姿态动作规则判断，无法稳定匹配时自动进入云端复核路径。
        </p>
      </div>

      <div class="top-strip">
        <article class="strip-card">
          <span>Device</span>
          <strong>{{ edgeStatus?.device_id ?? deviceId }}</strong>
        </article>
        <article class="strip-card">
          <span>Status</span>
          <strong :class="edgeStatus?.online ? 'ok' : 'warn'">{{ edgeStatus?.online ? 'ONLINE' : 'OFFLINE' }}</strong>
        </article>
        <article class="strip-card">
          <span>Pose</span>
          <strong>{{ actionLabel(activeAction) }}</strong>
        </article>
        <article class="strip-card">
          <span>Stream</span>
          <strong :class="rtcConnected ? 'ok' : 'warn'">{{ rtcConnected ? 'WebRTC' : (connected ? 'WS' : '--') }}</strong>
        </article>
      </div>
    </header>

    <main class="layout">
      <section class="panel viewport">
        <div class="panel-head">
          <div>
            <p class="kicker">Live Frame</p>
            <h2>实时画面与姿态框</h2>
          </div>
          <div class="panel-meta">
            <span v-if="rtcConnected" class="live-dot"></span>
            {{ rtcConnected ? 'WebRTC 实时视频' : '等待连接...' }}
          </div>
        </div>

        <div ref="frameRef" class="frame">
          <video
            ref="videoRef"
            class="frame-video"
            autoplay
            playsinline
            muted
          ></video>
          <div v-if="!rtcConnected" class="frame-placeholder">
            <div>
              <p>等待边端摄像头画面</p>
              <span>正在建立 WebRTC 视频连接；检测数据与视频使用不同通道</span>
            </div>
          </div>
          <div class="frame-grid"></div>

          <div v-if="latestDetection" class="frame-chips">
            <span>Frame {{ latestDetection.frame_id }}</span>
            <span>FPS {{ formatNumber(latestDetection.fps) }}</span>
            <span>{{ latestDetection.inference_ms }} ms</span>
            <span>{{ latestDetection.backend }}</span>
            <span>{{ latestDetection.model_task }}</span>
          </div>

          <div class="pose-badge" :class="{ alert: pose?.needs_cloud }">
            <strong>{{ actionLabel(activeAction) }}</strong>
            <span>{{ pose?.confidence ? `置信度 ${formatNumber(pose.confidence, 2)}` : '等待有效姿态' }}</span>
          </div>

          <div v-if="latestDetection" class="cloud-badge">
            <span>{{ cloudHint }}</span>
          </div>

          <div v-if="latestDetection" class="media-overlay" :style="mediaOverlayStyle">
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

        <div class="metrics">
          <article class="metric">
            <span>检测目标</span>
            <strong>{{ detections.length }}</strong>
          </article>
          <article class="metric">
            <span>推理耗时</span>
            <strong>{{ latestDetection ? `${formatNumber(latestDetection.inference_ms, 1)} ms` : '--' }}</strong>
          </article>
          <article class="metric">
            <span>云端候选</span>
            <strong>{{ pose?.needs_cloud ? 'YES' : 'NO' }}</strong>
          </article>
          <article class="metric">
            <span>最后更新</span>
            <strong>{{ latestDetection ? formatTime(latestDetection.created_at) : '--' }}</strong>
          </article>
        </div>
      </section>

      <aside class="panel rail">
        <div class="panel-head">
          <div>
            <p class="kicker">Control Deck</p>
            <h2>任务调度与复核</h2>
          </div>
        </div>

        <div v-if="error" class="notice error">{{ error }}</div>
        <div v-else-if="loading" class="notice">正在拉取边端状态...</div>

        <div class="field">
          <span>设备 ID</span>
          <input v-model="deviceId" type="text" />
        </div>

        <div class="field">
          <span>任务描述</span>
          <textarea v-model="taskText" rows="5"></textarea>
        </div>

        <button class="action" type="button" :disabled="scheduleBusy" @click="submitSchedule">
          {{ scheduleBusy ? '调度中...' : '预测调度位置' }}
        </button>

        <div v-if="scheduleResult" class="result-card">
          <p class="kicker">Decision</p>
          <h3>{{ scheduleResult.target }} / {{ scheduleResult.complexity }}</h3>
          <p>{{ scheduleResult.reason }}</p>
        </div>

        <div class="result-card accent">
          <p class="kicker">Pose Rule</p>
          <h3>{{ pose?.matched_rule || 'no_rule_matched' }}</h3>
          <p>{{ pose?.reason || '边端正在等待有效姿态动作。' }}</p>
        </div>

        <div class="evidence">
          <p class="kicker">Evidence</p>
          <ul v-if="pose?.evidence?.length">
            <li v-for="item in pose.evidence" :key="item">{{ item }}</li>
          </ul>
          <div v-else class="empty-inline">暂无规则证据。</div>
        </div>

        <div class="divider"></div>

        <div class="log-stack">
          <div class="panel-subhead">
            <h3>最近任务</h3>
            <span>{{ formatTime(latestLog(taskLogs)?.created_at) }}</span>
          </div>
          <article v-if="latestLog(taskLogs)" class="log-card">
            <strong>{{ latestLog(taskLogs)?.task }}</strong>
            <p>{{ latestLog(taskLogs)?.result_summary }}</p>
            <small>{{ latestLog(taskLogs)?.target }} · {{ latestLog(taskLogs)?.device_id }}</small>
          </article>
          <div v-else class="empty-inline">暂无任务日志。</div>
        </div>
      </aside>

      <section class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="kicker">Edge Timeline</p>
            <h2>边端状态与日志列表</h2>
          </div>
          <div class="panel-meta">
            <span v-if="connected" class="live-dot"></span>
            Server time: {{ formatTime(state?.server_time) }}
          </div>
        </div>

        <div class="timeline">
          <article v-for="log in taskLogs.slice(0, 6)" :key="log.task_id" class="timeline-item">
            <div class="timeline-top">
              <strong>{{ log.task }}</strong>
              <span>{{ log.target }}</span>
            </div>
            <p>{{ log.result_summary }}</p>
            <small>{{ log.device_id }} · {{ formatTime(log.created_at) }}</small>
          </article>
          <div v-if="!taskLogs.length" class="empty-inline">边端日志会在这里实时汇总。</div>
        </div>
      </section>
    </main>
  </div>
</template>
