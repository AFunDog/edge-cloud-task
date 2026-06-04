<script setup lang="ts">
import type { EdgeStatus } from '../types'
import { formatNumber, formatTime } from '../utils/format'

defineProps<{
  edgeStatus: EdgeStatus[]
}>()
</script>

<template>
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
</template>
