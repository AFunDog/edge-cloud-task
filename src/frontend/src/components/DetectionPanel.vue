<script setup lang="ts">
import { computed } from 'vue'
import type { DetectionResult } from '../types'
import { formatNumber, formatTime } from '../utils/format'

const props = defineProps<{
  latestDetection: DetectionResult | null
}>()

const detections = computed(() => props.latestDetection?.detections ?? [])

function boxStyle(item: DetectionResult['detections'][number]): Record<string, string> {
  const width = props.latestDetection?.frame_width || 640
  const height = props.latestDetection?.frame_height || 360
  return {
    left: `${Math.min((item.box.x1 / width) * 100, 96)}%`,
    top: `${Math.min((item.box.y1 / height) * 100, 92)}%`,
    width: `${Math.max(((item.box.x2 - item.box.x1) / width) * 100, 4)}%`,
    height: `${Math.max(((item.box.y2 - item.box.y1) / height) * 100, 6)}%`,
  }
}
</script>

<template>
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
        v-for="item in detections"
        :key="`${item.label}-${item.box.x1}-${item.box.y1}`"
        class="box"
        :style="boxStyle(item)"
      >
        <span>{{ item.label }} {{ formatNumber(item.confidence, 2) }}</span>
      </div>
    </div>

    <div class="table-wrap">
      <table v-if="detections.length">
        <thead>
          <tr>
            <th>Label</th>
            <th>Confidence</th>
            <th>Box</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in detections" :key="`${item.label}-${item.confidence}`">
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
</template>
