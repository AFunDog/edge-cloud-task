<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('cloudStation')!
const { events, pendingEvents, criticalEvents, analysisResults, dailyReport, dailyLoading, dailyReportMdUrl, selectedReport, reportError, openDailyReport, openReport, exportReport, eventTypeLabel, severityLabel, statusLabel, analysisFor, formatTime } = station
</script>

<template>
<main class="main main-events">
      <section class="events-board">
        <div class="events-summary">
          <div class="summary-tile">
            <span>总事件</span>
            <strong>{{ events.length }}</strong>
          </div>
          <div class="summary-tile warning">
            <span>待云端</span>
            <strong>{{ pendingEvents.length }}</strong>
          </div>
          <div class="summary-tile critical">
            <span>高风险</span>
            <strong>{{ criticalEvents.length }}</strong>
          </div>
          <div class="summary-tile">
            <span>分析报告</span>
            <strong>{{ analysisResults.length }}</strong>
          </div>
          <div class="summary-tile">
            <span>日报</span>
            <button class="daily-btn" type="button" @click="openDailyReport" :disabled="dailyLoading">
              {{ dailyLoading ? '生成中' : '查看/下载' }}
            </button>
          </div>
        </div>

        <div v-if="dailyReport" class="daily-report-section">
          <div class="daily-header">
            <strong>日报 {{ dailyReport.date }}</strong>
            <a :href="dailyReportMdUrl" target="_blank" class="download-link">下载 Markdown</a>
          </div>
          <div class="daily-grid">
            <div class="daily-stat">
              <span>事件总数</span>
              <strong>{{ dailyReport.total }}</strong>
            </div>
            <div class="daily-stat critical">
              <span>高风险</span>
              <strong>{{ dailyReport.by_severity?.critical ?? 0 }}</strong>
            </div>
            <div class="daily-stat warning">
              <span>警告</span>
              <strong>{{ dailyReport.by_severity?.warning ?? 0 }}</strong>
            </div>
            <div class="daily-stat">
              <span>待处理</span>
              <strong>{{ dailyReport.pending_count }}</strong>
            </div>
          </div>
          <div v-if="dailyReport.hazards?.length" class="daily-hazards">
            <span>隐患</span>
            <span v-for="h in dailyReport.hazards" :key="h.type" class="risk-chip" :class="h.severity">
              {{ h.type }} ({{ h.count }})
            </span>
          </div>
        </div>

        <div class="events-layout">
          <div class="event-list-panel">
            <div class="panel-title">异常事件与边云分工</div>
            <div v-if="events.length" class="event-list">
              <article v-for="event in events" :key="event.event_id" class="event-card" :class="event.severity">
                <div class="event-head">
                  <div>
                    <strong>{{ eventTypeLabel(event.event_type) }}</strong>
                    <div class="event-meta">{{ event.device_id }} · {{ formatTime(event.created_at) }}</div>
                  </div>
                  <div class="chip-row">
                    <span class="risk-chip" :class="event.severity">{{ severityLabel(event.severity) }}</span>
                    <span class="status-chip" :class="event.status">{{ statusLabel(event.status) }}</span>
                  </div>
                </div>
                <p>{{ event.summary }}</p>
                <div v-if="event.evidence.length" class="evidence-line">{{ event.evidence.slice(0, 2).join(' / ') }}</div>
                <div v-if="analysisFor(event)" class="event-analysis-link">
                  {{ analysisFor(event)?.conclusion }}
                </div>
                <div class="event-actions">
                  <button class="mini-btn" type="button" @click="openReport(event)">查看报告</button>
                </div>
              </article>
            </div>
            <div v-else class="empty-state">暂无事件。边端生成的本地事件和云端候选会显示在这里。</div>
          </div>

          <div class="analysis-panel">
            <div class="panel-title">云端 Agent 分析</div>
            <div v-if="reportError" class="report-error">{{ reportError }}</div>
            <article v-if="selectedReport" class="report-panel">
              <div class="event-head">
                <div>
                  <strong>事件报告</strong>
                  <div class="event-meta">{{ selectedReport.event.event_id }} · {{ formatTime(selectedReport.created_at) }}</div>
                </div>
                <button class="mini-btn primary" type="button" @click="exportReport(selectedReport)">导出 Markdown</button>
              </div>
              <pre>{{ selectedReport.report_markdown }}</pre>
            </article>
            <div v-if="analysisResults.length" class="analysis-list">
              <article v-for="item in analysisResults" :key="item.event_id" class="analysis-card" :class="item.risk_level">
                <div class="event-head">
                  <strong>{{ item.conclusion }}</strong>
                  <span class="risk-chip" :class="item.risk_level">{{ severityLabel(item.risk_level) }}</span>
                </div>
                <div class="analysis-section">
                  <span>判断依据</span>
                  <p>{{ item.reasoning.slice(0, 3).join('；') || '--' }}</p>
                </div>
                <div class="analysis-section">
                  <span>处置建议</span>
                  <p>{{ item.suggestions.slice(0, 3).join('；') || '--' }}</p>
                </div>
                <div class="event-meta">知识库 {{ item.used_knowledge ? 'YES' : 'NO' }} · 搜索 {{ item.used_search ? 'YES' : 'NO' }} · {{ formatTime(item.created_at) }}</div>
              </article>
            </div>
            <div v-else class="empty-state">云端分析报告会显示在这里。</div>
          </div>
        </div>
      </section>
    </main>
</template>
