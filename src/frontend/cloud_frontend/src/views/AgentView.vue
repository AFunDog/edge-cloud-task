<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('cloudStation')!
const {
  deviceId, chatQuestion, taskText, chatResult, chatLoading, chatHistory,
  scheduleResult, scanResult, scanning, submitChat, submitSchedule, submitScan,
  quickQuery, downloadReportMd, buildChatReportMd, printChatReport,
  renderMarkdown, formatTime,
} = station

function hasLogQuery(item: any): boolean {
  return item?.traces?.some((t: string) => t.startsWith('log_query') || t.startsWith('log_events'))
}
</script>

<template>
<main class="main main-settings">
      <div class="settings-page">
        <div class="settings-form">
          <div class="field">
            <label class="field-label">设备 ID</label>
            <input class="field-input" v-model="deviceId" type="text" />
          </div>
          <div class="field">
            <label class="field-label">快捷查询</label>
            <div class="quick-chips">
              <button type="button" class="chip-btn" @click="quickQuery('最近24小时有哪些异常事件？')">24h 异常</button>
              <button type="button" class="chip-btn" @click="quickQuery('分析当前的隐患趋势')">隐患分析</button>
              <button type="button" class="chip-btn" @click="quickQuery('统计各类型事件的分布情况')">事件统计</button>
              <button type="button" class="chip-btn" @click="submitScan" :disabled="scanning">{{ scanning ? '扫描中...' : '隐患扫描' }}</button>
            </div>
          </div>
          <div class="field">
            <label class="field-label">问题</label>
            <textarea class="field-textarea" v-model="chatQuestion" rows="4"></textarea>
          </div>
          <button class="btn btn-primary" type="button" :disabled="chatLoading" @click="submitChat">
            {{ chatLoading ? '正在分析...' : '发送到云端智能体' }}
          </button>
          <div style="height:1px;background:var(--border);margin:4px 0"></div>
          <div class="field">
            <label class="field-label">任务描述</label>
            <input class="field-input" v-model="taskText" type="text" />
          </div>
          <button class="btn btn-secondary" type="button" @click="submitSchedule">预测调度位置</button>
        </div>

        <div class="settings-results">
          <div v-if="scanResult" class="result-block">
            <div class="result-tag">隐患扫描报告</div>
            <div v-if="scanResult.hazards?.length" class="scan-hazards">
              <div v-for="(h, i) in scanResult.hazards" :key="i" class="scan-item" :class="h.severity">
                <span class="risk-chip" :class="h.severity">{{ h.severity }}</span>
                <strong>{{ h.type }}</strong>
                <span class="scan-count">{{ h.count }} 条</span>
                <p>{{ h.suggestion }}</p>
              </div>
            </div>
            <div v-else class="scan-clean">未发现明显隐患，系统运行正常。</div>
            <div v-if="scanResult.summary" class="scan-summary">
              统计：{{ scanResult.summary.total ?? 0 }} 条事件（过去 {{ scanResult.summary.period_hours ?? '--' }}h）
            </div>
          </div>

          <div v-if="chatLoading" class="result-block">
            <div class="result-tag">智能体分析中</div>
            <div class="result-body" style="color:var(--accent)">
              正在调用 AI 模型分析，请稍候...
            </div>
          </div>

          <div v-if="chatResult" class="result-block">
            <div class="result-tag">智能体回复</div>
            <div class="chat-reply-actions">
              <span class="source-badges">
                <span class="source-badge" :class="{ on: chatResult.used_knowledge }">知识库 {{ chatResult.used_knowledge ? '✓' : '✗' }}</span>
                <span class="source-badge" :class="{ on: chatResult.used_search }">搜索 {{ chatResult.used_search ? '✓' : '✗' }}</span>
                <span class="source-badge" :class="{ on: hasLogQuery(chatResult) }">日志 {{ hasLogQuery(chatResult) ? '✓' : '✗' }}</span>
              </span>
              <span style="display:flex;gap:6px">
                <button class="mini-btn" type="button" @click="downloadReportMd(buildChatReportMd(chatResult), `agent-${chatResult.id || Date.now()}.md`)">导出 MD</button>
                <button class="mini-btn" type="button" @click="printChatReport(chatResult)">导出 PDF</button>
              </span>
            </div>
            <div class="result-body md-content" v-html="renderMarkdown(chatResult.answer)"></div>
            <ul v-if="chatResult.traces?.length" class="trace-list">
              <li v-for="trace in chatResult.traces" :key="trace">{{ trace }}</li>
            </ul>
          </div>
          <div v-else-if="!chatLoading" class="empty-state">智能体回复会显示在这里</div>

          <div v-if="chatHistory.length" class="result-block">
            <div class="result-tag">对话历史</div>
            <div class="chat-history-list">
              <div v-for="item in chatHistory" :key="item.id" class="chat-history-item">
                <div class="chat-question">Q: {{ item.question }}</div>
                <div class="source-badges" style="margin-bottom:6px">
                  <span class="source-badge" :class="{ on: item.used_knowledge }">知识库 {{ item.used_knowledge ? '✓' : '✗' }}</span>
                  <span class="source-badge" :class="{ on: item.used_search }">搜索 {{ item.used_search ? '✓' : '✗' }}</span>
                </div>
                <div class="chat-answer md-content" v-html="renderMarkdown(item.answer)"></div>
                <div class="chat-actions">
                  <span class="event-meta">{{ item.device_id }} · {{ formatTime(item.created_at) }}</span>
                  <span style="display:flex;gap:6px">
                    <button class="mini-btn" type="button" @click="downloadReportMd(buildChatReportMd(item), `chat-${item.id}.md`)">MD</button>
                    <button class="mini-btn" type="button" @click="printChatReport(item)">PDF</button>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="scheduleResult" class="result-block">
            <div class="result-tag">调度决策</div>
            <div class="result-title">{{ scheduleResult.target }} / {{ scheduleResult.complexity }}</div>
            <div class="result-body">{{ scheduleResult.reason }}</div>
          </div>
        </div>
      </div>
    </main>
</template>
