import { useRef, useEffect, useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import { MessageSquare, Send } from 'lucide-react'
import clsx from 'clsx'

export default function MessagePanel() {
  const { messages, sendMessage, connectionState } = useTars()
  const containerRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')

  // Auto-scroll
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || connectionState !== 'connected') return
    sendMessage(text)
    setInput('')
  }, [input, sendMessage, connectionState])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  // Group messages by time proximity (60s window)
  const groupedMessages = messages.reduce<Array<{ messages: typeof messages; showTime: boolean }>>((acc, msg, i) => {
    const prev = i > 0 ? messages[i - 1] : null
    const sameGroup = prev && prev.sender === msg.sender && (msg.timestamp - prev.timestamp) < 60000
    if (sameGroup) {
      acc[acc.length - 1].messages.push(msg)
    } else {
      acc.push({ messages: [msg], showTime: true })
    }
    return acc
  }, [])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <MessageSquare size={13} className="text-signal-blue" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">iMessage</span>
        </div>
        <span className="text-[10px] text-slate-600">{messages.length}</span>
      </div>

      {/* Messages — conversation only */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-3 space-y-1">
        {groupedMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-600">
            <MessageSquare size={28} className="mb-2 opacity-30" />
            <p className="text-[10px]">No conversations yet</p>
            <p className="text-[9px] text-slate-700 mt-1">Send a message to start chatting</p>
          </div>
        ) : (
          groupedMessages.map((group, gi) => (
            <div key={gi} className="space-y-0.5">
              {group.showTime && group.messages[0] && (
                <div className={clsx(
                  'text-[9px] text-slate-700 mt-2 mb-1 px-1',
                  group.messages[0].sender === 'user' ? 'text-right' : 'text-left'
                )}>
                  {group.messages[0].time}
                </div>
              )}
              {group.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    'flex animate-fade-in',
                    msg.sender === 'user' ? 'justify-end' : 'justify-start'
                  )}
                >
                  <div className={clsx(
                    'max-w-[85%] px-3 py-2 text-[13px] leading-relaxed break-words',
                    msg.sender === 'user'
                      ? 'bg-signal-blue rounded-2xl rounded-br-sm text-white shadow-glow-blue'
                      : 'bg-void-700 rounded-2xl rounded-bl-sm text-slate-200 border border-panel-border'
                  )}>
                    {msg.text}
                  </div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Chat input */}
      <div className="px-2 py-2 border-t border-panel-border shrink-0">
        <div className="flex items-center gap-1.5 bg-void-800 border border-panel-border rounded-xl px-2.5 py-1.5 focus-within:border-signal-blue/50 focus-within:shadow-glow-blue transition-all">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message TARS..."
            className="flex-1 bg-transparent text-xs text-star-white placeholder-slate-600 outline-none min-w-0"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || connectionState !== 'connected'}
            className="shrink-0 text-signal-blue hover:text-signal-blue/80 disabled:text-slate-700 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={12} />
          </button>
        </div>
      </div>
    </div>
  )
}
