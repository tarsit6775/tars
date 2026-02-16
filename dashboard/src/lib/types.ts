// TARS Event types flowing through the WebSocket
export interface TarsEvent {
  type: string
  timestamp: string
  ts_unix: number
  data: Record<string, any>
}

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

export interface SubsystemStatus {
  websocket: 'connected' | 'reconnecting' | 'disconnected'
  agent: 'online' | 'working' | 'idle' | 'killed' | 'offline'
  mac: 'reachable' | 'unreachable'
  claude: 'active' | 'idle' | 'error'
}

export type TarsProcessStatus = 'stopped' | 'starting' | 'running' | 'stopping' | 'error' | 'killed' | 'unknown'

export interface TarsProcess {
  running: boolean
  pid: number | null
  started_at: number | null
  status: TarsProcessStatus
  uptime: number
  last_task?: string | null
}

export interface TarsStats {
  total_events: number
  total_tokens_in: number
  total_tokens_out: number
  total_cost: number
  actions_success: number
  actions_failed: number
  start_time: number
  uptime_seconds: number
  tool_usage: Record<string, number>
  model_usage: Record<string, number>
}

export interface TaskItem {
  id: number
  text: string
  time: string
  source: string
  status: 'active' | 'completed' | 'failed' | 'queued'
  startedAt: number
  completedAt?: number
}

export interface ThinkingBlock {
  id: string
  type: 'thinking' | 'tool_call' | 'tool_result' | 'error'
  model?: string
  text?: string
  toolName?: string
  toolInput?: any
  content?: string
  success?: boolean
  duration?: number
  time?: string
}

export interface ChatMessage {
  id: number
  text: string
  sender: 'tars' | 'user'
  time: string
  timestamp: number
}

export interface ActionLogEntry {
  id: number
  toolName: string
  detail: string
  success: boolean
  duration: number | null
  time: string
}

export interface OutputLine {
  stream: 'stdout' | 'stderr' | 'system' | 'event'
  text: string
  ts: number
  eventType?: string
}

export interface ControlCommand {
  type: 'control_command'
  command: 'start_tars' | 'stop_tars' | 'kill_tars' | 'restart_tars' | 'get_process_status' | 'send_task'
  data?: Record<string, any>
}
