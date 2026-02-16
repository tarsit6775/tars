import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { WebSocketManager } from '../lib/ws'
import { sendBrowserNotification } from '../lib/notifications'
import type {
  TarsEvent, ConnectionState, SubsystemStatus, TarsStats,
  TaskItem, ThinkingBlock, ChatMessage, ActionLogEntry,
  TarsProcess, OutputLine,
} from '../lib/types'

interface TarsContextValue {
  // Connection
  connectionState: ConnectionState
  subsystems: SubsystemStatus
  tunnelConnected: boolean
  // TARS Process
  tarsProcess: TarsProcess
  outputLog: OutputLine[]
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

  const taskIdRef = useRef(0)
  const msgIdRef = useRef(0)
  const actionIdRef = useRef(0)
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
      tarsProcess, outputLog,
      tasks, thinkingBlocks, messages, actionLog, stats, currentModel,
      memoryContext, memoryPreferences,
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
