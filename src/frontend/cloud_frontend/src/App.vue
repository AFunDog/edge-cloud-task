<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchState, scheduleTask, sendAgentChat } from './api'
import type { Detection, DetectionResult, SystemState, TaskLog } from './types'
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
const taskText = ref('车辆计数')
const chatResult = ref<any>(null)
const scheduleResult = ref<any>(null)
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
  timer = window.setInterval(loadState, 3000)
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
const latestDetection = computed(() => recentDetections.value[0] || null)
const serverTime = computed(() => formatTime(state.value?.server_time))
const activeTab = ref<'home' | 'settings' | 'logs'>('home')
const onlineEdgeCount = computed(() => edgeStatus.value.filter((item) => item.online).length)
const totalDetectionCount = computed(() => recentDetections.value.reduce((sum, item) => sum + (item.detections?.length || 0), 0))
const cloudStatus = computed(() => error.value ? 'DEGRADED' : 'ONLINE')
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

// ---------- 姿态关键点与骨架渲染辅助 ----------

interface PoseOverlay {
  points: NormalizedKeypoint[]
  edges: SkeletonEdge[]
}

/** 将单个检测的关键点归一化为容器内百分比，并计算可见骨架边。 */
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
</script>

<template>
  <div class="shell">
    <div class="mesh mesh-a"></div>
    <div class="mesh mesh-b"></div>
    <div class="mesh mesh-c"></div>

    <header class="masthead">
      <div class="masthead-copy">
        <p class="eyebrow">Cloud Station</p>
        <h1>云端协同控制台</h1>
        <p class="lede">
          汇总边端检测、智能体复核和任务调度结果。云端侧负责全局观察，边端侧继续保持实时采集与本地推理。
        </p>
      </div>

      <div class="top-strip">
        <article class="strip-card">
          <span>Cloud</span>
          <strong :class="error ? 'warn' : 'ok'">{{ cloudStatus }}</strong>
        </article>
        <article class="strip-card">
          <span>Edges</span>
          <strong>{{ onlineEdgeCount }}</strong>
        </article>
        <article class="strip-card">
          <span>Latest</span>
          <strong>{{ latestDetection ? latestDetection.detections.length : 0 }}</strong>
        </article>
        <article class="strip-card">
          <span>Targets</span>
          <strong>{{ totalDetectionCount }}</strong>
        </article>
      </div>
    </header>

    <nav class="tabbar" aria-label="云端控制台标签页">
      <button type="button" :class="{ active: activeTab === 'home' }" @click="activeTab = 'home'">
        <span>主页</span>
        <small>状态与检测</small>
      </button>
      <button type="button" :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">
        <span>设置</span>
        <small>智能体与调度</small>
      </button>
      <button type="button" :class="{ active: activeTab === 'logs' }" @click="activeTab = 'logs'">
        <span>日志</span>
        <small>任务记录</small>
      </button>
    </nav>

    <main class="layout">
      <section v-if="activeTab === 'home'" class="panel viewport">
        <div class="panel-head">
          <div>
            <p class="kicker">Live State</p>
            <h2>边端状态与实时检测</h2>
          </div>
          <div class="panel-meta">
            <span v-if="!error" class="live-dot"></span>
            Server time: {{ serverTime }}
          </div>
        </div>

        <div v-if="loading" class="notice">正在拉取系统状态...</div>
        <div v-else-if="error" class="notice error">{{ error }}</div>

        <div class="home-grid">
          <aside class="side-stack">
            <article class="result-card accent">
              <p class="kicker">Overview</p>
              <h3>{{ cloudStatus }}</h3>
              <p>在线边端 {{ onlineEdgeCount }} 台，最近缓存 {{ recentDetections.length }} 帧，总目标 {{ totalDetectionCount }} 个。</p>
            </article>

            <div v-if="edgeStatus.length" class="status-list">
              <article v-for="device in edgeStatus" :key="device.device_id" class="status-card">
                <div class="timeline-top">
                  <strong>{{ device.device_id }}</strong>
                  <span :class="device.online ? 'ok' : 'warn'">{{ device.online ? 'ONLINE' : 'OFFLINE' }}</span>
                </div>
                <div class="status-stats">
                  <span>FPS {{ formatNumber(device.fps) }}</span>
                  <span>CPU {{ formatNumber(device.cpu_percent) }}%</span>
                  <span>MEM {{ formatNumber(device.memory_percent) }}%</span>
                </div>
                <small>{{ device.network }} · {{ formatTime(device.last_seen) }}</small>
              </article>
            </div>
            <div v-else class="empty-inline">暂无边端在线。</div>
          </aside>

          <div class="detection-stage">
            <div ref="stageRef" class="frame">
              <img
                v-if="latestDetection?.image_jpeg_base64"
                class="frame-image"
                :src="`data:image/jpeg;base64,${latestDetection.image_jpeg_base64}`"
                alt="edge camera frame"
              />
              <div v-else class="frame-placeholder">
                <div>
                  <p>等待边端摄像头画面</p>
                  <span>检测数据会先进入云端状态缓存，画面预览取决于边端是否同步帧图像。</span>
                </div>
              </div>
              <div class="frame-grid"></div>

              <div v-if="latestDetection" class="frame-chips">
                <span>Frame {{ latestDetection.frame_id }}</span>
                <span>FPS {{ formatNumber(latestDetection.fps) }}</span>
                <span>{{ formatNumber(latestDetection.inference_ms, 1) }} ms</span>
                <span>{{ latestDetection.backend || '--' }}</span>
                <span>{{ formatTime(latestDetection.created_at) }}</span>
              </div>

              <div v-if="latestDetection?.pose" class="pose-badge" :class="{ alert: latestDetection.pose.needs_cloud }">
                <strong>{{ latestDetection.pose.action }}</strong>
                <span>{{ latestDetection.pose.needs_cloud ? '云端复核候选' : '边端规则稳定' }}</span>
              </div>

              <div v-if="latestDetection" class="media-overlay" :style="mediaOverlayStyle">
                <template v-for="(item, idx) in latestDetection.detections" :key="`pose-${idx}`">
                  <div
                    class="box"
                    :style="boxStyle(item)"
                  >
                    <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
                  </div>
                  <svg class="pose-layer" viewBox="0 0 100 100" preserveAspectRatio="none">
                    <line
                      v-for="(edge, ei) in poseOverlay(item).edges"
                      :key="ei"
                      :x1="edge.x1"
                      :y1="edge.y1"
                      :x2="edge.x2"
                      :y2="edge.y2"
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

            <div class="metrics">
              <article class="metric">
                <span>检测目标</span>
                <strong>{{ latestDetection ? latestDetection.detections.length : 0 }}</strong>
              </article>
              <article class="metric">
                <span>推理耗时</span>
                <strong>{{ latestDetection ? `${formatNumber(latestDetection.inference_ms, 1)} ms` : '--' }}</strong>
              </article>
              <article class="metric">
                <span>模型任务</span>
                <strong>{{ latestDetection?.model_task || '--' }}</strong>
              </article>
              <article class="metric">
                <span>设备</span>
                <strong>{{ latestDetection?.device_id || deviceId }}</strong>
              </article>
            </div>

            <div class="table-wrap log-scroll">
              <table v-if="latestDetection?.detections?.length">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Confidence</th>
                    <th>Box</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in latestDetection.detections" :key="`${item.label}-${item.confidence}`">
                    <td>{{ item.label }}</td>
                    <td>{{ formatNumber(item.confidence, 2) }}</td>
                    <td>
                      {{ item.box.x1.toFixed(0) }}, {{ item.box.y1.toFixed(0) }},
                      {{ item.box.x2.toFixed(0) }}, {{ item.box.y2.toFixed(0) }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="latestDetection" class="model-line">
                {{ latestDetection.model_path || 'model path unavailable' }}
              </div>
              <div v-else class="empty-inline">当前没有检测结果。</div>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'settings'" class="panel settings-panel">
        <div class="panel-head">
          <div>
            <p class="kicker">Agent Console</p>
            <h2>云端智能体与调度</h2>
          </div>
          <div class="panel-meta">使用当前最新检测上下文</div>
        </div>

        <div v-if="error" class="notice error">{{ error }}</div>

        <div class="settings-grid">
          <div class="settings-form">
            <label class="field">
              <span>设备 ID</span>
              <input v-model="deviceId" type="text" />
            </label>

            <label class="field">
              <span>问题</span>
              <textarea v-model="chatQuestion" rows="6"></textarea>
            </label>

            <button class="action" type="button" @click="submitChat">发送到云端智能体</button>

            <div class="divider"></div>

            <label class="field">
              <span>任务描述</span>
              <input v-model="taskText" type="text" />
            </label>

            <button class="action secondary" type="button" @click="submitSchedule">预测调度位置</button>
          </div>

          <div class="settings-result">
            <div v-if="chatResult" class="result-card accent">
              <p class="kicker">Answer</p>
              <h3>智能体回复</h3>
              <p>{{ chatResult.answer }}</p>
            </div>
            <div v-else class="empty-inline">智能体回复会显示在这里。</div>

            <div v-if="chatResult?.traces?.length" class="evidence">
              <p class="kicker">Traces</p>
              <ul>
                <li v-for="trace in chatResult.traces" :key="trace">{{ trace }}</li>
              </ul>
            </div>

            <div v-if="scheduleResult" class="result-card">
              <p class="kicker">Schedule</p>
              <h3>{{ scheduleResult.target }} / {{ scheduleResult.complexity }}</h3>
              <p>{{ scheduleResult.reason }}</p>
            </div>
          </div>
        </div>
      </section>

      <section v-else class="panel logs-panel">
        <div class="panel-head">
          <div>
            <p class="kicker">Operations Log</p>
            <h2>任务日志</h2>
          </div>
          <div class="panel-meta">{{ taskLogs.length }} records</div>
        </div>

        <div v-if="taskLogs.length" class="log-list">
          <article v-for="log in taskLogs" :key="log.task_id" class="log-card">
            <div class="timeline-top">
              <strong>{{ log.task }}</strong>
              <span>{{ log.target }}</span>
            </div>
            <p>{{ log.result_summary }}</p>
            <small>{{ log.device_id }} · {{ formatTime(log.created_at) }}</small>
          </article>
        </div>
        <div v-else class="empty-inline">暂无任务日志。</div>
      </section>
    </main>
  </div>
</template>
