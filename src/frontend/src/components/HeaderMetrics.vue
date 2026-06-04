<script setup lang="ts">
import { computed } from 'vue'
import type { DetectionResult, EdgeStatus } from '../types'

const props = defineProps<{
  error: string
  edgeStatus: EdgeStatus[]
  recentDetections: DetectionResult[]
}>()

const latestDetection = computed(() => props.recentDetections[0] || null)
const edgeOnlineCount = computed(() => props.edgeStatus.filter((item) => item.online).length)
const totalDetections = computed(() =>
  props.recentDetections.reduce((sum, item) => sum + (item.detections?.length || 0), 0),
)
</script>

<template>
  <div class="hero-metrics">
    <article class="metric">
      <span>云端状态</span>
      <strong>{{ error ? 'degraded' : 'online' }}</strong>
    </article>
    <article class="metric">
      <span>在线边端</span>
      <strong>{{ edgeOnlineCount }}</strong>
    </article>
    <article class="metric">
      <span>最近帧目标数</span>
      <strong>{{ latestDetection ? latestDetection.detections.length : 0 }}</strong>
    </article>
    <article class="metric">
      <span>总检测目标</span>
      <strong>{{ totalDetections }}</strong>
    </article>
  </div>
</template>
