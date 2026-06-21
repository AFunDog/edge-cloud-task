<script setup lang="ts">
import { inject, onActivated, onMounted } from 'vue'

const station = inject<Record<string, any>>('edgeStation')!
const { error, loading, rtcConnected, videoRef, frameRef, showVideoAnnotations, latestDetection, formatNumber, pose, actionLabel, activeAction, cloudHint, mediaOverlayStyle, detections, boxStyle, poseOverlay, keypointTitle, edgeStatus, deviceId, pendingEvents, events, analyzedEvents, hasUnauthorizedTime, hasExcessivePeople, hourNow, minuteNow, latestAnalysis, severityLabel, eventTypeLabel, statusLabel, taskLogs, formatTime, activateMonitor } = station

onMounted(() => { void activateMonitor() })
onActivated(() => { void activateMonitor() })
</script>

<template>
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
              <div class="metric-value small">{{ pendingEvents.length }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">边端事件</div>
              <div class="metric-value small">{{ events.length }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">云端分析</div>
              <div class="metric-value small">{{ analyzedEvents.length }}</div>
            </div>
          </div>
        </section>

        <section class="sidebar-section">
          <div class="sidebar-section-title">合理性检查</div>
          <div class="reasonability-grid">
            <div class="reasonability-item" :class="{ warn: hasUnauthorizedTime }">
              <span class="reasonability-icon">{{ hasUnauthorizedTime ? '!' : '&#10003;' }}</span>
              <span class="reasonability-label">时段合规</span>
            </div>
            <div class="reasonability-item" :class="{ warn: hasExcessivePeople }">
              <span class="reasonability-icon">{{ hasExcessivePeople ? '!' : '&#10003;' }}</span>
              <span class="reasonability-label">容量合规</span>
            </div>
          </div>
          <div class="reasonability-summary">
            当前 {{ detections.length }} 人 · 时段 {{ hourNow }}:{{ minuteNow }}
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
          <div class="sidebar-section-title">边云事件</div>
          <div v-if="events.length" class="event-list">
            <div v-for="event in events.slice(0, 5)" :key="event.event_id" class="event-item" :class="event.severity">
              <div class="event-head">
                <span class="event-name">{{ eventTypeLabel(event.event_type) }}</span>
                <span class="event-status" :class="event.status">{{ statusLabel(event.status) }}</span>
              </div>
              <div class="event-summary">{{ event.summary }}</div>
              <div class="event-meta">
                <span class="risk-chip" :class="event.severity">{{ severityLabel(event.severity) }}</span>
                {{ formatTime(event.created_at) }}
              </div>
            </div>
          </div>
          <div v-else class="no-data">边端事件会在这里实时汇总</div>

          <div class="section-divider"></div>
          <div class="sidebar-section-title">云端分析</div>
          <div v-if="latestAnalysis" class="analysis-item" :class="latestAnalysis.risk_level">
            <div class="event-head">
              <span class="event-name">{{ latestAnalysis.conclusion }}</span>
              <span class="risk-chip" :class="latestAnalysis.risk_level">{{ severityLabel(latestAnalysis.risk_level) }}</span>
            </div>
            <div class="event-summary">{{ latestAnalysis.suggestions.slice(0, 2).join('；') }}</div>
            <div class="event-meta">知识库 {{ latestAnalysis.used_knowledge ? 'YES' : 'NO' }} · 搜索 {{ latestAnalysis.used_search ? 'YES' : 'NO' }}</div>
          </div>
          <div v-else class="no-data">复杂事件的云端分析会显示在这里</div>

          <div class="section-divider"></div>
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
</template>
