import type { AgentRequest, AgentResponse, ScheduleDecision, SystemState, TaskRequest } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `HTTP ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function fetchState(): Promise<SystemState> {
  return request<SystemState>('/api/state')
}

export function sendAgentChat(payload: AgentRequest): Promise<AgentResponse> {
  return request<AgentResponse>('/api/agent/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function scheduleTask(payload: TaskRequest): Promise<ScheduleDecision> {
  return request<ScheduleDecision>('/api/tasks/schedule', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
