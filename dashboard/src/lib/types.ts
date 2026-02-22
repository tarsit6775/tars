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

// ── Email Types ──
export interface EmailMessage {
  id: number
  subject: string
  from: string
  to?: string
  date: string
  preview: string
  read: boolean
  flagged: boolean
  mailbox: string
  hasAttachment?: boolean
}

export interface EmailRule {
  id: string
  name: string
  enabled: boolean
  conditions: Record<string, string | boolean>
  actions: Record<string, string | boolean>
  hit_count: number
  created_at: string
}

export interface EmailScheduled {
  id: string
  to: string
  subject: string
  send_at: string
  status: 'pending' | 'sent' | 'cancelled'
}

export interface EmailStats {
  unread: number
  inbox_total: number
  sent_today: number
  drafts: number
  rules_count: number
  rules_triggered_today: number
  scheduled_pending: number
  snoozed_count: number
  ooo_active: boolean
  health_score: number
  inbox_zero_streak: number
  attachment_count: number
  vip_count: number
  security_threats: number
  pending_actions: number
  active_workflows: number
  compositions_today: number
  active_delegations: number
  overdue_delegations: number
  search_index_size: number
  sentiment_avg: number
  smart_folder_count: number
  threads_summarized: number
  labels_count: number
  newsletters_tracked: number
  auto_responses_active: number
  signatures_count: number
  aliases_count: number
  exports_count: number
  monitor_active: boolean
  top_senders: Array<{ name: string; count: number }>
}

export interface EmailEvent {
  id: number
  type: 'sent' | 'received' | 'rule_triggered' | 'batch_action' | 'scheduled_sent' | 'snoozed' | 'resurfaced' | 'digest' | 'ooo_set' | 'ooo_replied' | 'ooo_expired' | 'followup_overdue' | 'auto_digest' | 'action' | 'clean_sweep' | 'auto_triage' | 'unsubscribed' | 'vip_detected' | 'inbox_zero_progress' | 'attachment_indexed' | 'relationship_scored' | 'security_scan' | 'phishing_detected' | 'sender_blocked' | 'sender_trusted' | 'action_extracted' | 'meeting_extracted' | 'reminder_created' | 'action_completed' | 'workflow_created' | 'workflow_triggered' | 'workflow_completed' | 'email_composed' | 'email_rewritten' | 'email_proofread' | 'email_delegated' | 'delegation_completed' | 'delegation_nudged' | 'search_index_built' | 'email_search' | 'conversation_recalled' | 'sentiment_analyzed' | 'sentiment_alert' | 'smart_folder_created' | 'smart_folder_updated' | 'thread_summarized' | 'thread_decisions_extracted' | 'forward_summary_prepared' | 'label_added' | 'newsletters_detected' | 'auto_response_created' | 'signature_created' | 'alias_added' | 'emails_exported'
  detail: string
  time: string
  timestamp: number
}

export interface ControlCommand {
  type: 'control_command'
  command: 'start_tars' | 'stop_tars' | 'kill_tars' | 'restart_tars' | 'get_process_status' | 'send_task'
  data?: Record<string, any>
}
