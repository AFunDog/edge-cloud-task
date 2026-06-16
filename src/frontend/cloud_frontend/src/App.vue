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

onMounted(async () => {
  await loadState()
  timer = window.setInterval(loadState, 3000)
})

onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer)
  }
})

const recentDetections = computed(() => state.value?.recent_detections ?? [])
const edgeStatus = computed(() => state.value?.edge_status ?? [])
const taskLogs = computed(() => state.value?.task_logs ?? [])
const latestDetection = computed(() => recentDetections.value[0] || null)
const serverTime = computed(() => formatTime(state.value?.server_time))

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
      <div class="hero-metrics">
        <article class="metric">
          <span>云端状态</span>
          <strong>{{ error ? 'degraded' : 'online' }}</strong>
        </article>
        <article class="metric">
          <span>在线边端</span>
          <strong>{{ edgeStatus.filter((item) => item.online).length }}</strong>
        </article>
        <article class="metric">
          <span>最近帧目标数</span>
          <strong>{{ latestDetection ? latestDetection.detections.length : 0 }}</strong>
        </article>
        <article class="metric">
          <span>总检测目标</span>
          <strong>{{ recentDetections.reduce((sum, item) => sum + (item.detections?.length || 0), 0) }}</strong>
        </article>
      </div>
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
          <div class="state-column">
            <div v-if="edgeStatus.length" class="status-list">
              <article v-for="device in edgeStatus" :key="device.device_id" class="status-card">
                <div class="status-top">
                  <div>
                    <p>{{ device.device_id }}</p>
                    <span>{{ device.network }}</span>
                  </div>
                  <strong :class="device.online ? 'dot-ok' : 'dot-off'">
                    {{ device.online ? 'online' : 'offline' }}
                  </strong>
                </div>
                <div class="status-stats">
                  <span>FPS {{ formatNumber(device.fps) }}</span>
                  <span>CPU {{ formatNumber(device.cpu_percent) }}%</span>
                  <span>MEM {{ formatNumber(device.memory_percent) }}%</span>
                </div>
                <small>最后心跳 {{ formatTime(device.last_seen) }}</small>
              </article>
            </div>
            <div v-else class="empty-state">暂无边端在线。</div>
          </div>

          <div class="detection-stage">
            <div class="stage-frame">
              <img
                v-if="latestDetection?.image_jpeg_base64"
                class="stage-image"
                :src="`data:image/jpeg;base64,${latestDetection.image_jpeg_base64}`"
                alt="edge camera frame"
              />
              <div v-else class="stage-placeholder">等待边端摄像头画面</div>
              <div class="stage-grid"></div>
              <div class="scan-bar"></div>
              <div v-if="latestDetection" class="detection-tag">
                <span>Frame {{ latestDetection.frame_id }}</span>
                <span>FPS {{ formatNumber(latestDetection.fps) }}</span>
                <span>{{ latestDetection.inference_ms }} ms</span>
                <span>{{ latestDetection.backend }}</span>
                <span>{{ formatTime(latestDetection.created_at) }}</span>
              </div>

              <div
                v-for="item in latestDetection?.detections ?? []"
                :key="`${item.label}-${item.box.x1}-${item.box.y1}`"
                class="box"
                :style="boxStyle(item)"
              >
                <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
              </div>

              <!-- 姿态骨架与关键点 -->
              <template v-for="(item, idx) in latestDetection?.detections ?? []" :key="`pose-${idx}`">
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

            <div class="table-wrap">
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
              <div v-else class="empty-state">当前没有检测结果。</div>
            </div>
          </div>
        </div>
      </section>

      <aside class="panel">
        <div class="panel-head">
          <div>
            <p class="panel-kicker">Agent Console</p>
            <h2>云端智能体与调度</h2>
          </div>
        </div>

        <div v-if="error" class="state-line state-error">{{ error }}</div>

        <label class="field">
          <span>设备 ID</span>
          <input v-model="deviceId" type="text" />
        </label>

        <label class="field">
          <span>问题</span>
          <textarea v-model="chatQuestion" rows="5"></textarea>
        </label>

        <button class="action" type="button" @click="submitChat">发送到云端智能体</button>

        <div v-if="chatResult" class="answer-card">
          <p class="panel-kicker">Answer</p>
          <p>{{ chatResult.answer }}</p>
        </div>

        <div v-if="chatResult?.traces?.length" class="trace-card">
          <p class="panel-kicker">Traces</p>
          <ul>
            <li v-for="trace in chatResult.traces" :key="trace">{{ trace }}</li>
          </ul>
        </div>

        <div class="divider"></div>

        <label class="field">
          <span>任务描述</span>
          <input v-model="taskText" type="text" />
        </label>

        <button class="action secondary" type="button" @click="submitSchedule">预测调度位置</button>

        <div v-if="scheduleResult" class="answer-card">
          <p class="panel-kicker">Schedule</p>
          <p>{{ scheduleResult.target }} / {{ scheduleResult.complexity }}：{{ scheduleResult.reason }}</p>
        </div>
      </aside>

      <section class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="panel-kicker">Operations Log</p>
            <h2>任务日志</h2>
          </div>
        </div>

        <div v-if="taskLogs.length" class="log-list">
          <article v-for="log in taskLogs" :key="log.task_id" class="log-card">
            <div class="log-top">
              <strong>{{ log.task }}</strong>
              <span>{{ log.target }}</span>
            </div>
            <p>{{ log.result_summary }}</p>
            <small>{{ log.device_id }} · {{ formatTime(log.created_at) }}</small>
          </article>
        </div>
        <div v-else class="empty-state">暂无任务日志。</div>
      </section>
    </main>
  </div>
</template>
