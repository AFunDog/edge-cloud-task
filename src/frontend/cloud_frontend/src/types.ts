export interface BoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface Keypoint {
  x: number
  y: number
  confidence: number
  name?: string | null
}

export interface Detection {
  label: string
  confidence: number
  box: BoundingBox
  keypoints?: Keypoint[]
}

export interface PoseAnalysis {
  action:
    | 'standing'
    | 'sitting'
    | 'raising_hand'
    | 'crouching'
    | 'head_left'
    | 'head_right'
    | 'head_down'
    | 'upper_body_left'
    | 'upper_body_right'
    | 'unknown'
  confidence: number
  needs_cloud: boolean
  matched_rule: string
  reason: string
  evidence: string[]
}

export interface DetectionResult {
  device_id: string
  frame_id: string
  fps: number
  inference_ms: number
  backend: string
  model_path: string
  model_task: string
  frame_width: number
  frame_height: number
  image_jpeg_base64?: string | null
  detections: Detection[]
  pose?: PoseAnalysis | null
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

export type EventSeverity = 'info' | 'warning' | 'critical'
export type EventStatus = 'edge_resolved' | 'cloud_pending' | 'cloud_analyzed'

export interface SafetyEvent {
  event_id: string
  event_type: string
  device_id: string
  frame_id?: string | null
  severity: EventSeverity
  status: EventStatus
  summary: string
  evidence: string[]
  metrics: Record<string, unknown>
  created_at: string
}

export interface CloudAnalysisResponse {
  event_id: string
  risk_level: EventSeverity
  conclusion: string
  reasoning: string[]
  suggestions: string[]
  report: string
  used_search: boolean
  used_knowledge: boolean
  traces: string[]
  created_at: string
}

export interface SystemState {
  server_time: string
  edge_status: EdgeStatus[]
  recent_detections: DetectionResult[]
  task_logs: TaskLog[]
  events: SafetyEvent[]
  analysis_results: CloudAnalysisResponse[]
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
