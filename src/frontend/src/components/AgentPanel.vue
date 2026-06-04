<script setup lang="ts">
import { ref } from 'vue'
import { scheduleTask, sendAgentChat } from '../api'
import type { AgentResponse, ScheduleDecision } from '../types'

const emit = defineEmits<{
  stateChanged: []
}>()

const error = ref('')
const chatQuestion = ref('请分析当前边缘端画面是否存在异常，并给出调度建议。')
const deviceId = ref('edge-camera-01')
const taskText = ref('车辆计数')
const chatResult = ref<AgentResponse | null>(null)
const scheduleResult = ref<ScheduleDecision | null>(null)

async function submitChat(): Promise<void> {
  try {
    error.value = ''
    chatResult.value = await sendAgentChat({
      question: chatQuestion.value,
      device_id: deviceId.value,
      context: { source: 'web-console' },
    })
    emit('stateChanged')
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  }
}

async function submitSchedule(): Promise<void> {
  try {
    error.value = ''
    scheduleResult.value = await scheduleTask({
      task: taskText.value,
      device_id: deviceId.value,
      context: {},
    })
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : String(exc)
  }
}
</script>

<template>
  <aside class="panel">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">Agent Console</p>
        <h2>云端智能体与调度</h2>
      </div>
    </div>

    <div v-if="error" class="state-line state-error">{{ error }}</div>

    <label class="field">
      <span>设备 ID</span>
      <input v-model="deviceId" type="text" />
    </label>

    <label class="field">
      <span>问题</span>
      <textarea v-model="chatQuestion" rows="5"></textarea>
    </label>

    <button class="action" type="button" @click="submitChat">发送到云端智能体</button>

    <div v-if="chatResult" class="answer-card">
      <p class="panel-kicker">Answer</p>
      <p>{{ chatResult.answer }}</p>
    </div>

    <div v-if="chatResult?.traces.length" class="trace-card">
      <p class="panel-kicker">Traces</p>
      <ul>
        <li v-for="trace in chatResult.traces" :key="trace">{{ trace }}</li>
      </ul>
    </div>

    <div class="divider"></div>

    <label class="field">
      <span>任务描述</span>
      <input v-model="taskText" type="text" />
    </label>

    <button class="action secondary" type="button" @click="submitSchedule">预测调度位置</button>

    <div v-if="scheduleResult" class="answer-card">
      <p class="panel-kicker">Schedule</p>
      <p>{{ scheduleResult.target }} / {{ scheduleResult.complexity }}：{{ scheduleResult.reason }}</p>
    </div>
  </aside>
</template>
