import type {
  DetectionResult,
  EdgeStatus,
  ScheduleDecision,
  SystemState,
  TaskLog,
  TaskRequest,
} from './types'

const API_BASE_URL = import.meta.env.VITE_EDGE_API_BASE_URL ?? import.meta.env.VITE_API_BASE_URL ?? ''

// --------------- HTTP API ---------------

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

// --------------- WebSocket 实时流（检测数据、状态、日志） ---------------

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
    console.log(`[WS] 2s 后重连...`)
    reconnectTimer = window.setTimeout(connect, 2000)
  }

  function connect(): void {
    if (stopped) return
    console.log(`[WS] 正在连接 ${wsUrl}`)
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      console.error(`[WS] 创建 WebSocket 失败`, err)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      console.log(`[WS] 已连接`)
      callbacks.onOpen?.()
      const heartbeat = window.setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
      }, 30000)
      ws!.addEventListener('close', () => window.clearInterval(heartbeat), { once: true })
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data) as StreamMessage
        switch (msg.type) {
          case 'snapshot':
            console.log(`[WS] 收到快照，检测数=${msg.data.recent_detections?.length ?? 0}`)
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

    ws.onerror = (ev) => console.error(`[WS] 错误`, ev)
    ws.onclose = (ev) => {
      console.log(`[WS] 已断开 code=${ev.code}`)
      callbacks.onClose?.()
      if (!stopped) scheduleReconnect()
    }
  }

  connect()

  return {
    close: () => {
      stopped = true
      if (reconnectTimer !== null) { window.clearTimeout(reconnectTimer); reconnectTimer = null }
      if (ws !== null) { ws.onclose = null; ws.close(); ws = null }
    },
  }
}

// --------------- WebRTC 视频流 ---------------

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

  // 收到远端视频轨道 → 绑定到 <video>
  pc.ontrack = (event: RTCTrackEvent) => {
    console.log('[RTC] 收到视频轨道')
    videoElement.srcObject = event.streams[0] ?? new MediaStream([event.track])
    void videoElement.play().catch((err) => console.warn('[RTC] 视频自动播放失败', err))
  }

  // 本地 ICE 候选 → 发送给后端
  pc.onicecandidate = (event: RTCPeerConnectionIceEvent) => {
    if (!event.candidate || !pcId) return
    fetch(`${API_BASE_URL}/api/webrtc/candidate/${pcId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event.candidate),
    }).catch(() => {})
  }

  // 连接状态变化
  pc.onconnectionstatechange = () => {
    console.log(`[RTC] 连接状态: ${pc.connectionState}`)
    if (pc.connectionState === 'connected') {
      if (connectTimer !== null) window.clearTimeout(connectTimer)
      connectTimer = null
      onStateChange?.(true)
    } else if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
      onStateChange?.(false)
    }
  }

  // 视频元数据就绪 → 回调尺寸
  const onMeta = () => {
    onDimensionReady?.(videoElement.videoWidth || 640, videoElement.videoHeight || 360)
  }
  videoElement.addEventListener('loadedmetadata', onMeta, { once: true })

  // 生成 SDP offer
  const offer = await pc.createOffer({ offerToReceiveVideo: true })
  await pc.setLocalDescription(offer)
  await waitForIceGatheringComplete(pc)

  // 发送 offer → 后端
  console.log('[RTC] 发送 SDP offer')
  const resp = await fetch(`${API_BASE_URL}/api/webrtc/offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sdp: pc.localDescription!.sdp,
      type: pc.localDescription!.type,
    }),
  })
  if (!resp.ok) throw new Error(`WebRTC offer failed: HTTP ${resp.status}`)
  const answerData = await resp.json()
  pcId = answerData.pc_id

  // 设置远端 SDP（answer）
  await pc.setRemoteDescription(
    new RTCSessionDescription({ sdp: answerData.sdp, type: answerData.type }),
  )
  console.log('[RTC] 信令协商完成，等待媒体连接')
  connectTimer = window.setTimeout(() => {
    if (!stopped && pc.connectionState !== 'connected') {
      console.warn(`[RTC] 连接超时，当前状态: ${pc.connectionState}`)
      pc.close()
      onStateChange?.(false)
    }
  }, 8000)

  return {
    close: () => {
      stopped = true
      if (connectTimer !== null) window.clearTimeout(connectTimer)
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
