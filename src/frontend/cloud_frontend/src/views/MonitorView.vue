<script setup lang="ts">
import { computed, inject, onActivated, onMounted } from 'vue'

const station = inject<Record<string, any>>('cloudStation')!
const { latestDetection, rtcConnected, videoRef, stageRef, mediaOverlayStyle, boxStyle, poseOverlay, keypointTitle, formatNumber, formatTime, pendingEvents, events, analysisResults, latestAnalysis, severityLabel, edgeStatus, onlineEdgeCount, deviceId, latestEvent, eventTypeLabel, statusLabel, activateMonitor } = station
const edgeResolvedEvents = computed(() => events.value.filter((item: { status: string }) => item.status === 'edge_resolved'))

onMounted(() => { void activateMonitor() })
onActivated(() => { void activateMonitor() })
</script>

<template>
<main class="main main-home">
      <!-- Detection viewport -->
      <div class="viewport">
        <div ref="stageRef" class="frame-wrap">
          <video
            ref="videoRef"
            class="frame-video"
            autoplay playsinline muted
          ></video>
          <div v-if="!rtcConnected" class="frame-placeholder">
            <svg viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            <strong>等待边端 WebRTC 视频流</strong>
            <span>视频通过 WebRTC 直接从边端推送，数据通过云端 API 同步。</span>
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
              <strong>{{ edgeResolvedEvents.length }}</strong>
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
</template>
