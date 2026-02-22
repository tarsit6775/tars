import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { WebSocketManager } from '../lib/ws'
import { sendBrowserNotification } from '../lib/notifications'
import type {
  TarsEvent, ConnectionState, SubsystemStatus, TarsStats,
  TaskItem, ThinkingBlock, ChatMessage, ActionLogEntry,
  TarsProcess, OutputLine, EmailEvent, EmailStats,
} from '../lib/types'

interface InitStep {
  label: string
  detail: string
  status: 'ok' | 'fail' | 'skip'
  ts: number
}

interface TarsInitData {
  phase: 'complete'
  steps: InitStep[]
  environment: {
    battery?: string
    wifi?: string
    disk_free?: string
    volume?: string | number
    dark_mode?: boolean
    running_apps?: string[]
    screen_bounds?: string
    frontmost_app?: string
  }
  brain_llm: string
  agent_llm: string
  version: string
  uptime_start: number
}

interface TarsContextValue {
  // Connection
  connectionState: ConnectionState
  subsystems: SubsystemStatus
  tunnelConnected: boolean
  // TARS Process
  tarsProcess: TarsProcess
  outputLog: OutputLine[]
  // Init / Boot
  initData: TarsInitData | null
  // Data
  tasks: TaskItem[]
  thinkingBlocks: ThinkingBlock[]
  messages: ChatMessage[]
  actionLog: ActionLogEntry[]
  stats: TarsStats
  currentModel: string
  // Memory
  memoryContext: string
  memoryPreferences: string
  // Email
  emailEvents: EmailEvent[]
  emailStats: EmailStats
  // Control Actions
  startTars: (task?: string) => void
  stopTars: () => void
  killTars: () => void
  restartTars: (task?: string) => void
  // Data Actions
  sendTask: (task: string) => void
  sendMessage: (msg: string) => void
  killAgent: () => void
  updateConfig: (key: string, value: any) => void
  saveMemory: (field: string, content: string) => void
  requestMemory: () => void
  requestStats: () => void
  requestProcessStatus: () => void
  clearOutput: () => void
  setWsUrl: (url: string) => void
  setAuthToken: (token: string) => void
}

const defaultStats: TarsStats = {
  total_events: 0, total_tokens_in: 0, total_tokens_out: 0,
  total_cost: 0, actions_success: 0, actions_failed: 0,
  start_time: Date.now() / 1000, uptime_seconds: 0,
  tool_usage: {}, model_usage: {},
}

const defaultProcess: TarsProcess = {
  running: false,
  pid: null,
  started_at: null,
  status: 'stopped',
  uptime: 0,
  last_task: null,
}

const defaultEmailStats: EmailStats = {
  unread: 0, inbox_total: 0, sent_today: 0, drafts: 0,
  rules_count: 0, rules_triggered_today: 0, scheduled_pending: 0,
  monitor_active: false, top_senders: [],
}

const TarsContext = createContext<TarsContextValue | null>(null)

export function useTars() {
  const ctx = useContext(TarsContext)
  if (!ctx) throw new Error('useTars must be used within TarsProvider')
  return ctx
}

function getDefaultWsUrl(): string {
  const host = window.location.hostname
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (host === 'localhost' || host === '127.0.0.1') {
    return `ws://${host}:8421`
  }
  return `${protocol}//${window.location.host}/ws`
}

export function TarsProvider({ children }: { children: React.ReactNode }) {
  const wsRef = useRef<WebSocketManager | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [tunnelConnected, setTunnelConnected] = useState(false)
  const [tarsProcess, setTarsProcess] = useState<TarsProcess>(defaultProcess)
  const [outputLog, setOutputLog] = useState<OutputLine[]>([])
  const [subsystems, setSubsystems] = useState<SubsystemStatus>({
    websocket: 'disconnected', agent: 'offline', mac: 'unreachable', claude: 'idle',
  })
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [thinkingBlocks, setThinkingBlocks] = useState<ThinkingBlock[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [actionLog, setActionLog] = useState<ActionLogEntry[]>([])
  const [stats, setStats] = useState<TarsStats>(defaultStats)
  const [currentModel, setCurrentModel] = useState('--')
  const [memoryContext, setMemoryContext] = useState('')
  const [memoryPreferences, setMemoryPreferences] = useState('')
  const [emailEvents, setEmailEvents] = useState<EmailEvent[]>([])
  const [emailStats, setEmailStats] = useState<EmailStats>(defaultEmailStats)
  const [initData, setInitData] = useState<TarsInitData | null>(null)

  const taskIdRef = useRef(0)
  const msgIdRef = useRef(0)
  const actionIdRef = useRef(0)
  const emailEventIdRef = useRef(0)
  const blockIdRef = useRef(0)
  const currentThinkRef = useRef<string | null>(null)

  // Helper to append a log line
  const appendLog = useCallback((stream: OutputLine['stream'], text: string, eventType?: string) => {
    setOutputLog(prev => {
      const next = [...prev, { stream, text, ts: Date.now() / 1000, eventType }]
      return next.length > 2000 ? next.slice(-2000) : next
    })
  }, [])

  const handleEvent = useCallback((event: TarsEvent) => {
    const { type, data, timestamp } = event
    const time = new Date(timestamp).toLocaleTimeString()

    switch (type) {
      // ── Tunnel & Process Status ──
      case 'tunnel_status':
        setTunnelConnected(data.connected)
        setSubsystems(s => ({
          ...s,
          mac: data.connected ? 'reachable' : 'unreachable',
        }))
        if (!data.connected) {
          setTarsProcess(prev => ({ ...prev, running: false, status: 'unknown' }))
        }
        appendLog('system', data.connected ? '🔗 Mac tunnel connected' : '🔌 Mac tunnel disconnected', 'tunnel_status')
        break

      case 'tars_process_status':
        setTarsProcess(data as TarsProcess)
        setSubsystems(s => ({
          ...s,
          agent: data.running
            ? (data.status === 'running' ? 'working' : 'online')
            : data.status === 'killed' ? 'killed' : 'offline',
        }))
        break

      case 'tars_output': {
        const line: OutputLine = {
          stream: data.stream || 'stdout',
          text: data.text || '',
          ts: data.ts || Date.now() / 1000,
          eventType: 'tars_output',
        }
        setOutputLog(prev => {
          const next = [...prev, line]
          return next.length > 2000 ? next.slice(-2000) : next
        })
        break
      }

      case 'tars_output_batch': {
        const lines = (data.lines || []).map((l: any) => ({
          stream: l.stream || 'stdout',
          text: l.text || '',
          ts: l.ts || Date.now() / 1000,
          eventType: 'tars_output',
        }))
        setOutputLog(prev => {
          const next = [...prev, ...lines]
          return next.length > 2000 ? next.slice(-2000) : next
        })
        break
      }

      case 'command_response':
        break

      // ── Init / Boot Sequence ──
      case 'tars_init':
        setInitData(data as TarsInitData)
        setSubsystems(s => ({ ...s, agent: 'online' }))
        setTarsProcess(prev => ({ ...prev, running: true, status: 'running' }))
        appendLog('system', `🚀 TARS v${data.version} initialized — ${(data.steps || []).length} subsystems loaded`, 'tars_init')
        break

      // ── Task Events ──
      case 'task_received': {
        taskIdRef.current++
        const task: TaskItem = {
          id: taskIdRef.current,
          text: data.task,
          time,
          source: data.source || 'imessage',
          status: 'active',
          startedAt: Date.now(),
        }
        setTasks(prev => {
          const updated = prev.map(t => t.status === 'active' ? { ...t, status: 'completed' as const, completedAt: Date.now() } : t)
          return [task, ...updated]
        })
        setSubsystems(s => ({ ...s, agent: 'working' }))
        appendLog('event', `📋 New task: ${data.task}`, 'task')
        sendBrowserNotification('TARS // New Task', data.task)
        break
      }
      case 'task_completed':
        setTasks(prev => prev.map(t => t.status === 'active' ? { ...t, status: 'completed', completedAt: Date.now() } : t))
        setSubsystems(s => ({ ...s, agent: 'online' }))
        appendLog('event', `✅ Task complete`, 'task')
        sendBrowserNotification('TARS // Task Complete', data.response?.substring(0, 100) || 'Done')
        break

      // ── Thinking / Tool Events ──
      case 'thinking_start': {
        blockIdRef.current++
        const id = `think-${blockIdRef.current}`
        currentThinkRef.current = id
        setThinkingBlocks(prev => [...prev, {
          id, type: 'thinking', model: data.model || '', text: '',
        }])
        setCurrentModel(data.model || '')
        setSubsystems(s => ({ ...s, claude: 'active' }))
        appendLog('event', `🧠 Thinking... (${data.model || 'LLM'})`, 'thinking')
        break
      }
      case 'thinking':
        setThinkingBlocks(prev => {
          const idx = prev.findIndex(b => b.id === currentThinkRef.current)
          if (idx < 0) return prev
          const updated = [...prev]
          updated[idx] = { ...updated[idx], text: (updated[idx].text || '') + data.text }
          return updated
        })
        break

      case 'tool_called': {
        blockIdRef.current++
        currentThinkRef.current = null
        setThinkingBlocks(prev => [...prev, {
          id: `tool-${blockIdRef.current}`,
          type: 'tool_call',
          toolName: data.tool_name,
          toolInput: data.tool_input,
          time,
        }])
        const inputPreview = data.tool_input ? JSON.stringify(data.tool_input).substring(0, 120) : ''
        appendLog('event', `🔧 Tool: ${data.tool_name}${inputPreview ? ' → ' + inputPreview : ''}`, 'tool')
        break
      }
      case 'tool_result': {
        blockIdRef.current++
        setThinkingBlocks(prev => [...prev, {
          id: `result-${blockIdRef.current}`,
          type: 'tool_result',
          toolName: data.tool_name,
          content: data.content,
          success: data.success,
          duration: data.duration,
          time,
        }])
        actionIdRef.current++
        setActionLog(prev => [...prev, {
          id: actionIdRef.current,
          toolName: data.tool_name || '--',
          detail: String(data.content || '').substring(0, 200),
          success: data.success,
          duration: data.duration || null,
          time,
        }])
        setSubsystems(s => ({ ...s, claude: 'idle' }))
        const icon = data.success ? '✅' : '❌'
        const dur = data.duration != null ? ` (${data.duration.toFixed(1)}s)` : ''
        appendLog(data.success ? 'event' : 'stderr', `${icon} Result: ${data.tool_name}${dur} — ${String(data.content || '').substring(0, 150)}`, 'tool')
        break
      }

      // ── Message Events ──
      case 'imessage_sent':
        msgIdRef.current++
        setMessages(prev => [...prev, {
          id: msgIdRef.current, text: data.message, sender: 'tars', time, timestamp: Date.now(),
        }])
        appendLog('event', `💬 iMessage sent: ${data.message.substring(0, 100)}`, 'imessage')
        break
      case 'imessage_received':
        // Skip if this message came from the dashboard itself (already added locally by sendMessage)
        if (data.source === 'dashboard') break
        msgIdRef.current++
        setMessages(prev => [...prev, {
          id: msgIdRef.current, text: data.message, sender: 'user', time, timestamp: Date.now(),
        }])
        appendLog('event', `📱 iMessage received: ${data.message.substring(0, 100)}`, 'imessage')
        sendBrowserNotification('TARS // iMessage', data.message)
        break

      case 'api_call': {
        setCurrentModel(data.model || '')
        const tokensIn = data.tokens_in || 0
        const tokensOut = data.tokens_out || 0
        // Estimate cost (match server-side logic)
        const modelLower = (data.model || '').toLowerCase()
        let callCost = 0
        if (modelLower.includes('gemini') || modelLower.includes('llama')) {
          callCost = 0 // Free tiers
        } else if (modelLower.includes('haiku')) {
          callCost = (tokensIn * 0.80 + tokensOut * 4.00) / 1_000_000
        } else if (modelLower.includes('claude') || modelLower.includes('sonnet') || modelLower.includes('opus')) {
          callCost = (tokensIn * 3.00 + tokensOut * 15.00) / 1_000_000
        } else if (modelLower.includes('gpt-4')) {
          callCost = (tokensIn * 10.00 + tokensOut * 30.00) / 1_000_000
        }
        setStats(prev => ({
          ...prev,
          total_tokens_in: prev.total_tokens_in + tokensIn,
          total_tokens_out: prev.total_tokens_out + tokensOut,
          total_cost: prev.total_cost + callCost,
        }))
        appendLog('event', `🤖 API call: ${data.model || 'LLM'} (${tokensIn}→${tokensOut} tokens)`, 'api')
        break
      }

      case 'status_change':
        setSubsystems(s => ({ ...s, agent: data.status || 'online' }))
        appendLog('system', `⚡ Status: ${data.status || 'online'}`, 'status')
        break

      case 'error':
        blockIdRef.current++
        setThinkingBlocks(prev => [...prev, {
          id: `err-${blockIdRef.current}`, type: 'error', text: data.message || data.error || 'Unknown error',
        }])
        appendLog('stderr', `🚨 Error: ${data.message || data.error || 'Unknown error'}`, 'error')
        break

      case 'stats':
        setStats(data as TarsStats)
        break

      case 'memory_data':
        setMemoryContext(data.context || '')
        setMemoryPreferences(data.preferences || '')
        break

      case 'kill_switch':
        setSubsystems(s => ({ ...s, agent: 'killed' }))
        appendLog('stderr', `🛑 KILL SWITCH ACTIVATED`, 'kill')
        sendBrowserNotification('TARS // KILLED', 'Kill switch activated')
        break

      // ── Email Events ──
      case 'email_sent': {
        emailEventIdRef.current++
        const to = data.to ? (Array.isArray(data.to) ? data.to.join(', ') : data.to) : ''
        const subj = data.subject || ''
        const detail = data.action === 'reply'
          ? `↩️ Replied to message #${data.index || '?'}${data.reply_all ? ' (all)' : ''}`
          : data.action === 'forward'
          ? `➡️ Forwarded to ${data.to}`
          : `📤 Sent to ${to}: ${subj}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'sent' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, sent_today: s.sent_today + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_received': {
        emailEventIdRef.current++
        const sender = data.from || data.sender || 'Unknown'
        const subj = data.subject || 'No subject'
        const detail = `📬 From ${sender}: ${subj}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'received' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, unread: s.unread + 1, inbox_total: s.inbox_total + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        sendBrowserNotification('TARS // Email', `From ${sender}: ${subj}`)
        break
      }
      case 'email_rule_triggered': {
        emailEventIdRef.current++
        const ruleName = data.rule_name || data.rule || 'Unknown rule'
        const detail = `⚡ Rule "${ruleName}" triggered → ${data.actions_taken || data.action || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'rule_triggered' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, rules_triggered_today: s.rules_triggered_today + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_rule_added': {
        emailEventIdRef.current++
        const detail = `📋 Rule added: "${data.name || '?'}"`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'action' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, rules_count: s.rules_count + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_rule_notify': {
        const msg = data.message || data.subject || 'Email notification'
        appendLog('event', `📧 🔔 ${msg}`, 'email')
        sendBrowserNotification('TARS // Email Rule', msg)
        break
      }
      case 'email_batch_action': {
        emailEventIdRef.current++
        const action = data.action || 'action'
        const count = data.count || 0
        const detail = `📦 Batch ${action}: ${count} email${count !== 1 ? 's' : ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'batch_action' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_scheduled': {
        emailEventIdRef.current++
        const detail = `⏰ Scheduled: "${data.subject || '?'}" to ${data.to || '?'} at ${data.send_at || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'action' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, scheduled_pending: s.scheduled_pending + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_scheduled_sent': {
        emailEventIdRef.current++
        const detail = `✅ Scheduled email sent: "${data.subject || '?'}" to ${data.to || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'scheduled_sent' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, scheduled_pending: Math.max(0, s.scheduled_pending - 1) }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_action': {
        emailEventIdRef.current++
        const action = data.action || 'action'
        const detail = `📁 ${action}: message #${data.index || '?'}${data.to ? ` → ${data.to}` : ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'action' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_snoozed': {
        emailEventIdRef.current++
        const detail = `😴 Snoozed: "${data.subject || '?'}" until ${data.until || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'snoozed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, snoozed_count: (s.snoozed_count || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_resurfaced': {
        emailEventIdRef.current++
        const detail = `⏰ Resurfaced: "${data.subject || '?'}" from ${data.sender || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'resurfaced' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, snoozed_count: Math.max(0, (s.snoozed_count || 0) - 1) }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_digest': {
        emailEventIdRef.current++
        const detail = `📋 Daily digest generated (${data.sections || '?'} sections)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'digest' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_ooo_set': {
        emailEventIdRef.current++
        const detail = `🏖️ OOO set: ${data.start || '?'} → ${data.end || '?'} (${data.status || 'active'})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'ooo_set' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, ooo_active: true }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_ooo_replied': {
        emailEventIdRef.current++
        const detail = `🏖️ OOO auto-reply → ${data.to || 'unknown'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'ooo_replied' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_ooo_expired':
      case 'email_ooo_cancelled': {
        emailEventIdRef.current++
        const label = type === 'email_ooo_expired' ? 'expired' : 'cancelled'
        const detail = `🏖️ OOO ${label} — auto-replied to ${data.replied_to_count || 0} sender(s)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'ooo_expired' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(s => ({ ...s, ooo_active: false }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_followup_overdue': {
        emailEventIdRef.current++
        const detail = `📋 ${data.count || '?'} follow-up(s) overdue`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'followup_overdue' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_auto_digest': {
        emailEventIdRef.current++
        const detail = `📰 Auto-digest generated for ${data.date || 'today'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'auto_digest' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_clean_sweep': {
        emailEventIdRef.current++
        const detail = `🧹 Clean sweep: ${data.archived || 0} archived, ${data.previewed || 0} previewed`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'clean_sweep' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_auto_triage': {
        emailEventIdRef.current++
        const detail = `📊 Auto-triaged ${data.count || 0} emails`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'auto_triage' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_unsubscribed': {
        emailEventIdRef.current++
        const detail = `🚫 Unsubscribe detected for ${data.sender || 'unknown'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'unsubscribed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_vip_detected': {
        emailEventIdRef.current++
        const detail = `⭐ VIP detected: ${data.contact || 'unknown'} (score: ${data.score || '?'})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'vip_detected' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'inbox_zero_progress': {
        emailEventIdRef.current++
        const detail = `📥 Inbox: ${data.total || 0} emails (${data.trend || 'stable'})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'inbox_zero_progress' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_security_scan': {
        emailEventIdRef.current++
        const detail = `🛡️ Security scan: ${data.risk_level || 'unknown'} risk (score: ${data.phishing_score || 0})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'security_scan' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'phishing_detected':
      case 'suspicious_link_found': {
        emailEventIdRef.current++
        const detail = `🚨 Phishing alert: ${data.sender || 'unknown sender'} — score ${data.phishing_score || data.count || '?'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'phishing_detected' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'sender_blocked': {
        emailEventIdRef.current++
        const detail = `🚫 Sender blocked: ${data.email || 'unknown'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'sender_blocked' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'sender_trusted': {
        emailEventIdRef.current++
        const detail = `✅ Sender trusted: ${data.email || 'unknown'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'sender_trusted' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'action_item_extracted': {
        emailEventIdRef.current++
        const detail = `📋 ${data.count || 1} action items from: ${data.subject || 'email'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'action_extracted' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'meeting_extracted': {
        emailEventIdRef.current++
        const detail = `📅 Meeting found: ${data.subject || 'unknown'} (${data.platform || 'unknown'})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'meeting_extracted' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'reminder_created':
      case 'calendar_event_created': {
        emailEventIdRef.current++
        const detail = `⏰ ${type === 'reminder_created' ? 'Reminder' : 'Event'}: ${data.title || 'untitled'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'reminder_created' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'action_completed': {
        emailEventIdRef.current++
        const detail = `✅ Action completed: ${data.task || data.action_id || 'unknown'}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'action_completed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'workflow_created': {
        emailEventIdRef.current++
        const detail = `🔗 Workflow created: ${data.name || 'unnamed'} (${data.step_count || 0} steps)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'workflow_created' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'workflow_triggered': {
        emailEventIdRef.current++
        const detail = `⚡ Workflow triggered: ${data.name || 'unnamed'} (${data.trigger_reason || 'manual'})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'workflow_triggered' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'workflow_completed': {
        emailEventIdRef.current++
        const detail = `✅ Workflow done: ${data.steps || 0} steps executed`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'workflow_completed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_composed': {
        emailEventIdRef.current++
        const detail = `🖊️ Composed: ${data.tone || 'formal'} tone, ${data.style || 'concise'} style`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'email_composed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_rewritten': {
        emailEventIdRef.current++
        const detail = `✏️ Rewritten: ${data.tone || 'formal'} tone`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'email_rewritten' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_proofread': {
        emailEventIdRef.current++
        const detail = `🔍 Proofread: ${data.issues || 0} issues found`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'email_proofread' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_delegated': {
        emailEventIdRef.current++
        const detail = `📋 Delegated to ${data.delegate_to || 'someone'}: ${data.subject || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'email_delegated' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'delegation_completed': {
        emailEventIdRef.current++
        const detail = `✅ Delegation completed: ${data.delegation_id || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'delegation_completed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'delegation_nudged': {
        emailEventIdRef.current++
        const detail = `⏰ Delegation nudged: ${data.delegate_to || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'delegation_nudged' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'search_index_built': {
        emailEventIdRef.current++
        const detail = `🔍 Search index rebuilt: ${data.indexed || 0} emails indexed`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'search_index_built' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_search': {
        emailEventIdRef.current++
        const detail = `🔎 Search: ${data.query || ''} (${data.results || 0} results)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'email_search' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'conversation_recalled': {
        emailEventIdRef.current++
        const detail = `💬 Conversation recalled: ${data.contact || ''} (${data.count || 0} emails)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'conversation_recalled' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_sentiment_analyzed': {
        emailEventIdRef.current++
        const detail = `🎭 Sentiment: ${data.label || 'neutral'} (score ${data.score ?? 0}) — ${data.subject || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'sentiment_analyzed' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_sentiment_alert': {
        emailEventIdRef.current++
        const detail = `⚠️ Negative sentiment alert: score ${data.score ?? 0} — ${data.subject || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'sentiment_alert' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'smart_folder_created': {
        emailEventIdRef.current++
        const detail = `📂 Smart folder created: ${data.name || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'smart_folder_created' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'smart_folder_updated': {
        emailEventIdRef.current++
        const detail = `📂 Smart folder updated: ${data.name || data.folder_id || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'smart_folder_updated' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'thread_summarized': {
        emailEventIdRef.current++
        const detail = `📝 Thread summarized: ${data.subject || ''} (${data.message_count || 0} messages)`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'thread_summarized' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'thread_decisions_extracted': {
        emailEventIdRef.current++
        const detail = `🔍 Thread decisions: ${data.count || 0} decisions from "${data.subject || ''}"`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'thread_decisions_extracted' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'forward_summary_prepared': {
        emailEventIdRef.current++
        const detail = `📤 Forward summary: "${data.subject || ''}" for ${data.recipient || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'forward_summary_prepared' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'label_added': {
        emailEventIdRef.current++
        const detail = `🏷️ Label "${data.label || ''}" added to: ${data.subject || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'label_added' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(prev => ({ ...prev, labels_count: (prev.labels_count || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'newsletters_detected': {
        emailEventIdRef.current++
        const detail = `📰 Detected ${data.count || 0} newsletters from ${data.sources || 0} sources`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'newsletters_detected' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'auto_response_created': {
        emailEventIdRef.current++
        const detail = `🤖 Auto-response created: "${data.name || ''}" (${data.id || ''})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'auto_response_created' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(prev => ({ ...prev, auto_responses_active: (prev.auto_responses_active || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'signature_created': {
        emailEventIdRef.current++
        const detail = `✍️ Signature created: "${data.name || ''}" (${data.sig_id || ''})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'signature_created' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(prev => ({ ...prev, signatures_count: (prev.signatures_count || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'alias_added': {
        emailEventIdRef.current++
        const detail = `🎭 Alias added: ${data.email || ''} (${data.display_name || ''})`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'alias_added' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(prev => ({ ...prev, aliases_count: (prev.aliases_count || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'emails_exported': {
        emailEventIdRef.current++
        const detail = `📦 Exported ${data.count || 0} emails (${data.format || 'json'}) to ${data.file || ''}`
        setEmailEvents(prev => {
          const next = [...prev, { id: emailEventIdRef.current, type: 'emails_exported' as const, detail, time, timestamp: Date.now() }]
          return next.length > 200 ? next.slice(-200) : next
        })
        setEmailStats(prev => ({ ...prev, exports_count: (prev.exports_count || 0) + 1 }))
        appendLog('event', `📧 ${detail}`, 'email')
        break
      }
      case 'email_stats': {
        setEmailStats(data as EmailStats)
        break
      }

      default: {
        // Catch any unknown event types and still log them
        const preview = JSON.stringify(data).substring(0, 150)
        appendLog('event', `[${type}] ${preview}`, type)
        break
      }
    }
  }, [appendLog])

  // Initialize WebSocket
  useEffect(() => {
    const ws = new WebSocketManager(getDefaultWsUrl())
    wsRef.current = ws

    ws.onStateChange((state) => {
      setConnectionState(state)
      setSubsystems(s => ({
        ...s,
        websocket: state === 'connected' ? 'connected' : state === 'reconnecting' ? 'reconnecting' : 'disconnected',
      }))
    })

    ws.onEvent(handleEvent)
    ws.connect()

    return () => ws.disconnect()
  }, [handleEvent])

  // Periodic stats + process status refresh
  useEffect(() => {
    const interval = setInterval(() => {
      if (connectionState === 'connected') {
        wsRef.current?.send({ type: 'get_stats' })
        wsRef.current?.send({ type: 'get_process_status' })
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [connectionState])

  // ── Control Actions ──
  const startTars = useCallback((task?: string) => {
    wsRef.current?.send({
      type: 'control_command',
      command: 'start_tars',
      data: task ? { task } : {},
    })
    setTarsProcess(prev => ({ ...prev, status: 'starting' }))
  }, [])

  const stopTars = useCallback(() => {
    wsRef.current?.send({
      type: 'control_command',
      command: 'stop_tars',
    })
    setTarsProcess(prev => ({ ...prev, status: 'stopping' }))
  }, [])

  const killTars = useCallback(() => {
    wsRef.current?.send({
      type: 'control_command',
      command: 'kill_tars',
    })
    setTarsProcess(prev => ({ ...prev, status: 'killed' }))
  }, [])

  const restartTars = useCallback((task?: string) => {
    wsRef.current?.send({
      type: 'control_command',
      command: 'restart_tars',
      data: task ? { task } : {},
    })
    setTarsProcess(prev => ({ ...prev, status: 'starting' }))
  }, [])

  const sendTask = useCallback((task: string) => {
    wsRef.current?.send({ type: 'send_task', task })
  }, [])

  const sendMessage = useCallback((msg: string) => {
    wsRef.current?.send({ type: 'send_message', message: msg })
    msgIdRef.current++
    setMessages(prev => [...prev, {
      id: msgIdRef.current, text: msg, sender: 'user', time: new Date().toLocaleTimeString(), timestamp: Date.now(),
    }])
  }, [])

  const killAgent = useCallback(() => {
    wsRef.current?.send({ type: 'kill' })
    setSubsystems(s => ({ ...s, agent: 'killed' }))
  }, [])

  const updateConfig = useCallback((key: string, value: any) => {
    wsRef.current?.send({ type: 'update_config', key, value })
  }, [])

  const saveMemory = useCallback((field: string, content: string) => {
    wsRef.current?.send({ type: 'save_memory', field, content })
  }, [])

  const requestMemoryFn = useCallback(() => {
    wsRef.current?.send({ type: 'get_memory' })
  }, [])

  const requestStatsFn = useCallback(() => {
    wsRef.current?.send({ type: 'get_stats' })
  }, [])

  const requestProcessStatus = useCallback(() => {
    wsRef.current?.send({ type: 'get_process_status' })
  }, [])

  const clearOutput = useCallback(() => {
    setOutputLog([])
  }, [])

  const setWsUrl = useCallback((url: string) => {
    wsRef.current?.updateUrl(url)
  }, [])

  const setAuthToken = useCallback((token: string) => {
    wsRef.current?.updateToken(token)
  }, [])

  return (
    <TarsContext.Provider value={{
      connectionState, subsystems, tunnelConnected,
      tarsProcess, outputLog, initData,
      tasks, thinkingBlocks, messages, actionLog, stats, currentModel,
      memoryContext, memoryPreferences,
      emailEvents, emailStats,
      startTars, stopTars, killTars, restartTars,
      sendTask, sendMessage, killAgent, updateConfig, saveMemory,
      requestMemory: requestMemoryFn, requestStats: requestStatsFn,
      requestProcessStatus, clearOutput,
      setWsUrl, setAuthToken,
    }}>
      {children}
    </TarsContext.Provider>
  )
}
