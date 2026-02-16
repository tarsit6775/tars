import { TarsEvent, ConnectionState } from './types'

type EventHandler = (event: TarsEvent) => void
type StateHandler = (state: ConnectionState) => void

export class WebSocketManager {
  private ws: WebSocket | null = null
  private url: string
  private token: string | null
  private handlers: Set<EventHandler> = new Set()
  private stateHandlers: Set<StateHandler> = new Set()
  private _state: ConnectionState = 'disconnected'
  private reconnectAttempts = 0
  private maxReconnectDelay = 30000
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private messageQueue: string[] = []
  private lastPong = 0

  constructor(url: string, token?: string | null) {
    this.url = url
    this.token = token || null
  }

  get state(): ConnectionState {
    return this._state
  }

  private setState(s: ConnectionState) {
    this._state = s
    this.stateHandlers.forEach(h => h(s))
  }

  connect() {
    if (this._state === 'connected' || this._state === 'connecting') return
    this.setState('connecting')
    this.createSocket()
  }

  disconnect() {
    this.stopHeartbeat()
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout)
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
    this.setState('disconnected')
  }

  private createSocket() {
    try {
      const url = this.token ? `${this.url}?token=${this.token}` : this.url
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        this.setState('connected')
        this.startHeartbeat()
        this.flushQueue()
        this.send({ type: 'get_stats' })
        this.send({ type: 'get_memory' })
      }

      this.ws.onmessage = (e) => {
        try {
          if (e.data === 'pong') {
            this.lastPong = Date.now()
            return
          }
          const event: TarsEvent = JSON.parse(e.data)
          this.handlers.forEach(h => h(event))
        } catch {
          // ignore parse errors
        }
      }

      this.ws.onclose = () => {
        this.stopHeartbeat()
        this.ws = null
        this.scheduleReconnect()
      }

      this.ws.onerror = () => {
        // onclose will fire after this
      }
    } catch {
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect() {
    this.setState('reconnecting')
    this.reconnectAttempts++
    const baseDelay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay)
    const jitter = Math.random() * 1000
    const delay = baseDelay + jitter
    this.reconnectTimeout = setTimeout(() => this.createSocket(), delay)
  }

  private startHeartbeat() {
    this.lastPong = Date.now()
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping')
        // If no pong in 10s, reconnect
        if (Date.now() - this.lastPong > 30000) {
          this.ws?.close()
        }
      }
    }, 15000)
  }

  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  private flushQueue() {
    while (this.messageQueue.length > 0) {
      const msg = this.messageQueue.shift()!
      this.ws?.send(msg)
    }
  }

  send(data: Record<string, any>) {
    const msg = JSON.stringify(data)
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(msg)
    } else {
      this.messageQueue.push(msg)
    }
  }

  onEvent(handler: EventHandler) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  onStateChange(handler: StateHandler) {
    this.stateHandlers.add(handler)
    return () => this.stateHandlers.delete(handler)
  }

  updateUrl(url: string) {
    this.url = url
    if (this._state !== 'disconnected') {
      this.disconnect()
      this.connect()
    }
  }

  updateToken(token: string) {
    this.token = token
  }
}
