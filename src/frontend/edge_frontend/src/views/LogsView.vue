<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('edgeStation')!
const { error, loading, taskLogs, events, latestAnalysis, formatTime, eventTypeLabel, statusLabel, severityLabel } = station
</script>

<template>
  <main class="main main-logs">
    <div class="logs-page">
      <div class="logs-header">
        <h2 class="logs-title">边端日志</h2>
        <span class="logs-count">{{ taskLogs.length }} records</span>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-else-if="loading" class="notice">正在拉取边端状态...</div>
      <div v-if="events.length" class="event-list" style="margin-bottom:14px">
        <div v-for="event in events" :key="event.event_id" class="event-item" :class="event.severity">
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
      <div v-if="latestAnalysis" class="analysis-item" :class="latestAnalysis.risk_level" style="margin-bottom:14px">
        <div class="event-head">
          <span class="event-name">{{ latestAnalysis.conclusion }}</span>
          <span class="risk-chip" :class="latestAnalysis.risk_level">{{ severityLabel(latestAnalysis.risk_level) }}</span>
        </div>
        <div class="event-summary">{{ latestAnalysis.suggestions.slice(0, 2).join('；') }}</div>
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
      <div v-else class="empty-state">边端日志会在这里实时汇总</div>
    </div>
  </main>
</template>
