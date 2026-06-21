<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('edgeStation')!
const { pose, activeAction, actionLabel, latestDetection, detections, pendingEvents, analyzedEvents, hasUnauthorizedTime, hasExcessivePeople, hourNow, minuteNow, cloudHint, formatNumber } = station
</script>

<template>
  <main class="main main-logs">
    <div class="settings-page">
      <section class="result-block">
        <div class="result-tag">姿态识别</div>
        <div class="result-title">{{ actionLabel(activeAction) }}</div>
        <div class="result-body">{{ cloudHint }}</div>
        <div class="metric-grid" style="margin-top:14px">
          <div class="metric-card">
            <div class="metric-label">检测目标</div>
            <div class="metric-value">{{ detections.length }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">姿态置信度</div>
            <div class="metric-value small">{{ pose?.confidence ? formatNumber(pose.confidence, 2) : '--' }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">推理耗时</div>
            <div class="metric-value small">{{ latestDetection ? formatNumber(latestDetection.inference_ms, 1) + 'ms' : '--' }}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">云端候选</div>
            <div class="metric-value small">{{ pendingEvents.length }}</div>
          </div>
        </div>
      </section>
      <section class="result-block">
        <div class="result-tag">合理性检查</div>
        <div class="reasonability-grid">
          <div class="reasonability-item" :class="{ warn: hasUnauthorizedTime }">
            <span class="reasonability-icon">{{ hasUnauthorizedTime ? '!' : '✓' }}</span>
            <span class="reasonability-label">时段合规</span>
          </div>
          <div class="reasonability-item" :class="{ warn: hasExcessivePeople }">
            <span class="reasonability-icon">{{ hasExcessivePeople ? '!' : '✓' }}</span>
            <span class="reasonability-label">容量合规</span>
          </div>
        </div>
        <div class="reasonability-summary">当前 {{ detections.length }} 人 · 时段 {{ hourNow }}:{{ minuteNow }} · 已分析 {{ analyzedEvents.length }}</div>
      </section>
    </div>
  </main>
</template>
