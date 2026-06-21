<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('cloudStation')!
const { taskLogs, formatTime } = station
</script>

<template>
<main class="main main-logs">
      <div class="logs-page">
        <div class="logs-header">
          <h2 class="logs-title">任务日志</h2>
          <span class="logs-count">{{ taskLogs.length }} records</span>
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
        <div v-else class="empty-state">暂无任务日志</div>
      </div>
    </main>
</template>
