import type { AgentRequest, AgentResponse, EventReport, ScheduleDecision, SystemState, TaskRequest } from './types'

const API_BASE_URL = import.meta.env.VITE_CLOUD_API_BASE_URL ?? import.meta.env.VITE_API_BASE_URL ?? ''

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

export function fetchEventReport(eventId: string): Promise<EventReport> {
  return request<EventReport>(`/api/events/${encodeURIComponent(eventId)}/report`)
}

export function scanHazards(hours: number = 168): Promise<{
  summary: Record<string, unknown>
  hazards: Array<Record<string, unknown>>
  recent_events: Array<Record<string, unknown>>
}> {
  return request(`/api/agent/scan?hours=${hours}`)
}

export function fetchDailyReport(dateStr: string = ''): Promise<Record<string, unknown>> {
  const params = dateStr ? `?d=${encodeURIComponent(dateStr)}` : ''
  return request(`/api/reports/daily${params}`)
}

export function getDailyReportMdUrl(dateStr: string = ''): string {
  const params = dateStr ? `?d=${encodeURIComponent(dateStr)}&fmt=md` : '?fmt=md'
  return `${API_BASE_URL}/api/reports/daily${params}`
}
