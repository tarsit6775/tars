import { useRef, useEffect, useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import { ChevronDown, Search, Wrench, CheckCircle2, XCircle, Zap, Brain } from 'lucide-react'
import clsx from 'clsx'

function ModelBadge({ model }: { model: string }) {
  const isHaiku = model.includes('haiku')
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider',
      isHaiku
        ? 'bg-signal-purple/20 text-signal-purple border border-signal-purple/30'
        : 'bg-signal-cyan/20 text-signal-cyan border border-signal-cyan/30'
    )}>
      {isHaiku ? <Zap size={9} /> : <Brain size={9} />}
      {isHaiku ? 'HAIKU' : 'SONNET'}
    </span>
  )
}

function ToolCallBlock({ block }: { block: any }) {
  const [expanded, setExpanded] = useState(false)
  const isResult = block.type === 'tool_result'
  const success = block.success

  return (
    <div className={clsx(
      'rounded-lg border overflow-hidden my-2 animate-fade-in',
      isResult
        ? success ? 'border-signal-green/30 bg-signal-green/5' : 'border-signal-red/30 bg-signal-red/5'
        : 'border-panel-border bg-panel-surface'
    )}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs font-semibold hover:bg-white/[0.02] transition-colors"
      >
        {isResult ? (
          success ? <CheckCircle2 size={12} className="text-signal-green" /> : <XCircle size={12} className="text-signal-red" />
        ) : (
          <Wrench size={12} className="text-thrust" />
        )}
        <span className={isResult ? (success ? 'text-signal-green' : 'text-signal-red') : 'text-thrust'}>
          {isResult ? 'Result: ' : ''}{block.toolName}
        </span>
        {block.duration != null && (
          <span className="text-[10px] text-slate-600 ml-auto mr-2">{block.duration.toFixed(1)}s</span>
        )}
        {block.time && <span className="text-[10px] text-slate-700">{block.time}</span>}
        <ChevronDown size={12} className={clsx('text-slate-600 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="px-3 py-2 border-t border-panel-border text-[11px] text-slate-400 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
          {isResult ? String(block.content || '').substring(0, 1000) : JSON.stringify(block.toolInput, null, 2)}
        </div>
      )}
    </div>
  )
}

export default function ThinkingStream() {
  const { thinkingBlocks } = useTars()
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState('')
  const [showFilter, setShowFilter] = useState(false)

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [thinkingBlocks, autoScroll])

  // Detect manual scroll
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    setAutoScroll(atBottom)
  }, [])

  const jumpToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  const filteredBlocks = filter
    ? thinkingBlocks.filter(b =>
        (b.text && b.text.toLowerCase().includes(filter.toLowerCase())) ||
        (b.toolName && b.toolName.toLowerCase().includes(filter.toLowerCase()))
      )
    : thinkingBlocks

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <Brain size={13} className="text-signal-cyan" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Thinking</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowFilter(!showFilter)} className="text-slate-500 hover:text-slate-300">
            <Search size={12} />
          </button>
          <span className="text-[10px] text-slate-600">{thinkingBlocks.length} blocks</span>
        </div>
      </div>

      {showFilter && (
        <div className="px-3 py-2 border-b border-panel-border shrink-0">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by text or tool name..."
            className="w-full bg-void-800 border border-panel-border rounded px-2 py-1 text-xs text-star-white placeholder-slate-600 outline-none focus:border-signal-cyan/50"
          />
        </div>
      )}

      {/* Stream */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 space-y-1"
      >
        {filteredBlocks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-600">
            <Brain size={32} className="mb-3 opacity-30" />
            <p className="text-xs">Waiting for TARS to begin thinking...</p>
          </div>
        ) : (
          filteredBlocks.map((block) => {
            if (block.type === 'thinking') {
              return (
                <div key={block.id} className="animate-fade-in">
                  {block.model && <ModelBadge model={block.model} />}
                  <div className="mt-1.5 text-[13px] leading-relaxed text-slate-200 whitespace-pre-wrap break-words">
                    {block.text}
                    {/* Blinking cursor for active block */}
                    {block.id === `think-${thinkingBlocks.filter(b => b.type === 'thinking').length}` && (
                      <span className="inline-block w-1.5 h-4 bg-signal-cyan ml-0.5 animate-typing" />
                    )}
                  </div>
                </div>
              )
            }
            if (block.type === 'tool_call' || block.type === 'tool_result') {
              return <ToolCallBlock key={block.id} block={block} />
            }
            if (block.type === 'error') {
              return (
                <div key={block.id} className="flex items-start gap-2 p-2 rounded bg-signal-red/10 border border-signal-red/30 animate-fade-in">
                  <XCircle size={14} className="text-signal-red mt-0.5 shrink-0" />
                  <span className="text-xs text-signal-red">{block.text}</span>
                </div>
              )
            }
            return null
          })
        )}
      </div>

      {/* Jump to bottom */}
      {!autoScroll && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-4 right-4 z-10 flex items-center gap-1 px-2.5 py-1 rounded-full glass text-[10px] font-semibold text-signal-cyan border border-signal-cyan/30 hover:bg-signal-cyan/10 transition-colors"
        >
          <ChevronDown size={10} />
          Latest
        </button>
      )}
    </div>
  )
}
