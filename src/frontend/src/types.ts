export interface BoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface Detection {
  label: string
  confidence: number
  box: BoundingBox
}

export interface DetectionResult {
  device_id: string
  frame_id: string
  fps: number
  inference_ms: number
  backend: string
  model_path: string
  frame_width: number
  frame_height: number
  image_jpeg_base64?: string | null
  detections: Detection[]
  created_at: string
}

export interface EdgeStatus {
  device_id: string
  online: boolean
  network: string
  fps: number
  cpu_percent: number
  memory_percent: number
  last_seen: string
}

export interface TaskLog {
  task_id: string
  task: string
  device_id: string
  target: 'edge' | 'cloud'
  result_summary: string
  created_at: string
}

export interface SystemState {
  server_time: string
  edge_status: EdgeStatus[]
  recent_detections: DetectionResult[]
  task_logs: TaskLog[]
}

export interface AgentRequest {
  question: string
  device_id?: string
  context: Record<string, unknown>
}

export interface AgentResponse {
  answer: string
  used_search: boolean
  used_knowledge: boolean
  traces: string[]
}

export interface TaskRequest {
  task: string
  device_id: string
  frame_id?: string | null
  context: Record<string, unknown>
}

export interface ScheduleDecision {
  target: 'edge' | 'cloud'
  complexity: 'simple' | 'complex'
  reason: string
}
