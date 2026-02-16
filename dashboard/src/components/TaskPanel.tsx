import { useState, useRef, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import { Terminal, Send, ListTodo, Loader2, CheckCircle2, XCircle, MessageSquare, Globe, Laptop } from 'lucide-react'
import clsx from 'clsx'

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  imessage: <MessageSquare size={10} />,
  dashboard: <Globe size={10} />,
  cli: <Terminal size={10} />,
  agent: <Laptop size={10} />,
}

export default function TaskPanel() {
  const { tasks, sendTask, connectionState } = useTars()
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || connectionState !== 'connected') return
    sendTask(text)
    setInput('')
  }, [input, sendTask, connectionState])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <ListTodo size={13} className="text-thrust" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Tasks</span>
        </div>
        <span className="text-[10px] text-slate-600">{tasks.length}</span>
      </div>

      {/* Command input */}
      <div className="px-2 py-2 border-b border-panel-border shrink-0">
        <div className="flex items-center gap-1.5 bg-void-800 border border-panel-border rounded-lg px-2.5 py-1.5 focus-within:border-signal-cyan/50 focus-within:shadow-glow-cyan transition-all">
          <Terminal size={12} className="text-slate-600 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter task..."
            className="flex-1 bg-transparent text-xs text-star-white placeholder-slate-600 outline-none min-w-0"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || connectionState !== 'connected'}
            className="shrink-0 text-signal-cyan hover:text-signal-cyan/80 disabled:text-slate-700 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={12} />
          </button>
        </div>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-600">
            <ListTodo size={28} className="mb-2 opacity-30" />
            <p className="text-[10px]">No tasks yet</p>
          </div>
        ) : (
          tasks.map(task => (
            <div
              key={task.id}
              className={clsx(
                'rounded-lg px-3 py-2.5 border-l-2 transition-all animate-fade-in',
                task.status === 'active' && 'border-l-thrust bg-thrust/5 border border-l-2 border-thrust/20',
                task.status === 'completed' && 'border-l-signal-green bg-signal-green/[0.03] opacity-60',
                task.status === 'failed' && 'border-l-signal-red bg-signal-red/[0.03]',
                task.status === 'queued' && 'border-l-slate-600 bg-white/[0.01]',
              )}
            >
              <div className="flex items-start gap-2">
                <div className="mt-0.5 shrink-0">
                  {task.status === 'active' && <Loader2 size={12} className="text-thrust animate-spin" />}
                  {task.status === 'completed' && <CheckCircle2 size={12} className="text-signal-green" />}
                  {task.status === 'failed' && <XCircle size={12} className="text-signal-red" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-star-white leading-snug break-words">{task.text}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[9px] text-slate-600">{task.time}</span>
                    <span className="flex items-center gap-0.5 text-[9px] text-slate-600">
                      {SOURCE_ICONS[task.source] || SOURCE_ICONS.agent}
                      {task.source}
                    </span>
                    <span className="text-[9px] text-slate-700">#{task.id}</span>
                    {task.status === 'completed' && task.completedAt && task.startedAt && (
                      <span className="text-[9px] text-signal-green/70">
                        {((task.completedAt - task.startedAt) / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
