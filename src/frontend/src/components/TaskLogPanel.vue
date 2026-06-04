<script setup lang="ts">
import type { TaskLog } from '../types'
import { formatTime } from '../utils/format'

defineProps<{
  taskLogs: TaskLog[]
}>()
</script>

<template>
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
</template>
