<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { connectStream, connectWebRTC, fetchState, scheduleTask } from './api'
import type { Detection, DetectionResult, EdgeStatus, SystemState, TaskLog } from './types'
import { formatNumber, formatTime } from './utils/format'

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
const videoRef = ref<HTMLVideoElement | null>(null)

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
  if (!videoRef.value) return
  try {
    rtcControl = await connectWebRTC(
      videoRef.value,
      (w, h) => { videoWidth.value = w; videoHeight.value = h },
    )
    rtcConnected.value = true
  } catch (exc) {
    console.error('[RTC] 连接失败', exc)
  }
}

onMounted(async () => {
  await loadInitialState()
  openStream()
  await openWebRTC()
})

onBeforeUnmount(() => {
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

function boxStyle(item: Detection, _current: DetectionResult | null): Record<string, string> {
  return {
    left: `${Math.min((item.box.x1 / videoWidth.value) * 100, 96)}%`,
    top: `${Math.min((item.box.y1 / videoHeight.value) * 100, 92)}%`,
    width: `${Math.max(((item.box.x2 - item.box.x1) / videoWidth.value) * 100, 4)}%`,
    height: `${Math.max(((item.box.y2 - item.box.y1) / videoHeight.value) * 100, 6)}%`,
  }
}

function actionLabel(value: string): string {
  const map: Record<string, string> = {
    standing: '站立', sitting: '坐下', raising_hand: '举手', crouching: '蹲下', unknown: '待复核',
  }
  return map[value] ?? value
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

        <div class="frame">
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
              <span>启动边端服务器和采集进程后，这里会显示实时视频</span>
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

          <div
            v-for="item in detections"
            :key="`${item.label}-${item.box.x1}-${item.box.y1}`"
            class="box"
            :style="boxStyle(item, latestDetection)"
          >
            <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
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
