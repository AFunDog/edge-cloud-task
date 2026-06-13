import type {
  DetectionResult,
  EdgeStatus,
  ScheduleDecision,
  SystemState,
  TaskLog,
  TaskRequest,
} from './types'

const API_BASE_URL = import.meta.env.VITE_EDGE_API_BASE_URL ?? import.meta.env.VITE_API_BASE_URL ?? ''

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

export function scheduleTask(payload: TaskRequest): Promise<ScheduleDecision> {
  return request<ScheduleDecision>('/api/tasks/schedule', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// --------------- WebSocket 实时流 ---------------

export type StreamMessage =
  | { type: 'snapshot'; data: SystemState }
  | { type: 'detection'; data: DetectionResult }
  | { type: 'status'; data: EdgeStatus }
  | { type: 'task_log'; data: TaskLog }
  | { type: 'error'; message: string }

export interface StreamCallbacks {
  onDetection?: (data: DetectionResult) => void
  onStatus?: (data: EdgeStatus) => void
  onSnapshot?: (data: SystemState) => void
  onTaskLog?: (data: TaskLog) => void
  onError?: (message: string) => void
  onClose?: () => void
  onOpen?: () => void
}

export function connectStream(callbacks: StreamCallbacks): { close: () => void } {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/stream`
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null
  let stopped = false

  function scheduleReconnect(): void {
    if (stopped) return
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    console.log(`[Stream] 2s 后重连...`)
    reconnectTimer = window.setTimeout(connect, 2000)
  }

  function connect(): void {
    if (stopped) return
    console.log(`[Stream] 正在连接 ${wsUrl}`)
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      console.error(`[Stream] 创建 WebSocket 失败`, err)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      console.log(`[Stream] 已连接`)
      callbacks.onOpen?.()

      // 每 30 秒发送心跳保活
      const heartbeat = window.setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 30000)

      ws!.addEventListener('close', () => {
        window.clearInterval(heartbeat)
      }, { once: true })
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data) as StreamMessage
        switch (msg.type) {
          case 'snapshot':
            console.log(`[Stream] 收到快照，检测数=${msg.data.recent_detections?.length ?? 0}`)
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
          case 'error':
            callbacks.onError?.(msg.message)
            break
        }
      } catch {
        // 忽略无法解析的消息
      }
    }

    ws.onerror = (ev) => {
      console.error(`[Stream] WebSocket 错误`, ev)
    }

    ws.onclose = (ev) => {
      console.log(`[Stream] 已断开 code=${ev.code} reason=${ev.reason}`)
      callbacks.onClose?.()
      if (!stopped) {
        scheduleReconnect()
      }
    }
  }

  connect()

  return {
    close: () => {
      stopped = true
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

