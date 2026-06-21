import type {
  AgentRequest,
  AgentResponse,
  CloudAnalysisResponse,
  DetectionResult,
  EdgeStatus,
  EventReport,
  SafetyEvent,
  ScheduleDecision,
  SystemState,
  TaskLog,
  TaskRequest,
} from './types'

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

export function fetchChatHistory(limit: number = 20): Promise<
  Array<{
    id: number
    question: string
    answer: string
    device_id: string
    traces: string[]
    used_knowledge: boolean
    used_search: boolean
    created_at: string
  }>
> {
  return request(`/api/agent/history?limit=${limit}`)
}

export function fetchKnowledgeFiles(): Promise<Array<{ name: string; size: number }>> {
  return request('/api/knowledge')
}

export function fetchKnowledgeFile(name: string): Promise<{ name: string; suffix: string; content: string; size: number }> {
  return request(`/api/knowledge/${encodeURIComponent(name)}`)
}

export function saveKnowledgeFile(name: string, content: string): Promise<{ name: string; size: number; ok: boolean }> {
  return request(`/api/knowledge/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

// --------------- WebRTC 视频流（连接边端） ---------------

const EDGE_BASE_URL = 'http://localhost:8001'

// --------------- 边端 WebSocket 实时流（检测数据、状态、日志） ---------------

export type StreamMessage =
  | { type: 'snapshot'; data: SystemState }
  | { type: 'detection'; data: DetectionResult }
  | { type: 'status'; data: EdgeStatus }
  | { type: 'task_log'; data: TaskLog }
  | { type: 'event'; data: SafetyEvent }
  | { type: 'analysis_result'; data: CloudAnalysisResponse }
  | { type: 'error'; message: string }

export interface StreamCallbacks {
  onDetection?: (data: DetectionResult) => void
  onSnapshot?: (data: SystemState) => void
  onStatus?: (data: EdgeStatus) => void
  onTaskLog?: (data: TaskLog) => void
  onEvent?: (data: SafetyEvent) => void
  onAnalysisResult?: (data: CloudAnalysisResponse) => void
  onError?: (message: string) => void
  onOpen?: () => void
  onClose?: () => void
}

export function connectStream(callbacks: StreamCallbacks): { close: () => void } {
  const wsUrl = edgeWebSocketUrl('/api/stream')
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null
  let heartbeatTimer: number | null = null
  let stopped = false

  function clearHeartbeat(): void {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function scheduleReconnect(): void {
    if (stopped) return
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    reconnectTimer = window.setTimeout(connect, 2000)
  }

  function connect(): void {
    if (stopped) return
    try {
      ws = new WebSocket(wsUrl)
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      callbacks.onOpen?.()
      clearHeartbeat()
      heartbeatTimer = window.setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
      }, 30000)
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data) as StreamMessage
        switch (msg.type) {
          case 'snapshot':
            callbacks.onSnapshot?.(msg.data)
            break
          case 'detection':
            callbacks.onDetection?.(msg.data)
            break
          case 'status':
            callbacks.onStatus?.(msg.data)
            break
          case 'task_log':
            callbacks.onTaskLog?.(msg.data)
            break
          case 'event':
            callbacks.onEvent?.(msg.data)
            break
          case 'analysis_result':
            callbacks.onAnalysisResult?.(msg.data)
            break
          case 'error':
            callbacks.onError?.(msg.message)
            break
        }
      } catch {
        // ignore malformed stream messages
      }
    }

    ws.onerror = () => {}
    ws.onclose = () => {
      clearHeartbeat()
      callbacks.onClose?.()
      if (!stopped) scheduleReconnect()
    }
  }

  connect()

  return {
    close: () => {
      stopped = true
      clearHeartbeat()
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (ws !== null) {
        ws.onclose = null
        ws.close()
        ws = null
      }
    },
  }
}

function edgeWebSocketUrl(path: string): string {
  const url = new URL(EDGE_BASE_URL, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = path
  url.search = ''
  url.hash = ''
  return url.toString()
}

export async function connectWebRTC(
  videoElement: HTMLVideoElement,
  onDimensionReady?: (w: number, h: number) => void,
  onStateChange?: (connected: boolean) => void,
): Promise<{ close: () => void }> {
  console.log('[RTC] 创建 PeerConnection')
  const pc = new RTCPeerConnection()
  let pcId = ''
  let stopped = false
  let connectTimer: number | null = null
  let videoPlaying = false

  const markVideoPlaying = () => {
    videoPlaying = true
    if (connectTimer !== null) window.clearTimeout(connectTimer)
    connectTimer = null
    onStateChange?.(true)
  }
  videoElement.addEventListener('playing', markVideoPlaying)

  pc.ontrack = (event: RTCTrackEvent) => {
    console.log('[RTC] 收到视频轨道')
    videoElement.srcObject = event.streams[0] ?? new MediaStream([event.track])
    void videoElement.play().catch((err) => console.warn('[RTC] 视频自动播放失败', err))
  }

  pc.onicecandidate = (event: RTCPeerConnectionIceEvent) => {
    if (!event.candidate || !pcId) return
    fetch(`${EDGE_BASE_URL}/api/webrtc/candidate/${pcId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event.candidate),
    }).catch(() => {})
  }

  pc.onconnectionstatechange = () => {
    console.log(`[RTC] 连接状态: ${pc.connectionState}`)
    if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
      onStateChange?.(false)
    }
  }

  const onMeta = () => {
    onDimensionReady?.(videoElement.videoWidth || 640, videoElement.videoHeight || 360)
  }
  videoElement.addEventListener('loadedmetadata', onMeta, { once: true })

  const offer = await pc.createOffer({ offerToReceiveVideo: true })
  await pc.setLocalDescription(offer)
  await waitForIceGatheringComplete(pc)

  console.log('[RTC] 发送 SDP offer')
  const resp = await fetch(`${EDGE_BASE_URL}/api/webrtc/offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp: pc.localDescription!.sdp, type: pc.localDescription!.type }),
  })
  if (!resp.ok) throw new Error(`WebRTC offer failed: HTTP ${resp.status}`)
  const answerData = await resp.json()
  pcId = answerData.pc_id

  await pc.setRemoteDescription(new RTCSessionDescription({ sdp: answerData.sdp, type: answerData.type }))
  console.log('[RTC] 信令协商完成，等待媒体连接')
  connectTimer = window.setTimeout(() => {
    if (!stopped && !videoPlaying) {
      console.warn(`[RTC] 首帧超时，当前连接状态: ${pc.connectionState}`)
      pc.close()
      onStateChange?.(false)
    }
  }, 8000)

  return {
    close: () => {
      stopped = true
      if (connectTimer !== null) window.clearTimeout(connectTimer)
      videoElement.removeEventListener('playing', markVideoPlaying)
      onStateChange?.(false)
      videoElement.srcObject = null
      pc.close()
    },
  }
}

function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    const timeout = window.setTimeout(done, 3000)
    function done(): void {
      window.clearTimeout(timeout)
      pc.removeEventListener('icegatheringstatechange', onStateChange)
      resolve()
    }
    function onStateChange(): void {
      if (pc.iceGatheringState === 'complete') done()
    }
    pc.addEventListener('icegatheringstatechange', onStateChange)
  })
}
