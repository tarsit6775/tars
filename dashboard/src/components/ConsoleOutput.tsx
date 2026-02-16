import { useRef, useEffect, useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import { Activity, ChevronDown, Trash2, Download } from 'lucide-react'
import clsx from 'clsx'

type FilterType = 'all' | 'events' | 'output' | 'errors'

export default function ConsoleOutput() {
  const { outputLog, clearOutput, tunnelConnected } = useTars()
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState<FilterType>('all')

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [outputLog, autoScroll])

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

  const handleDownload = useCallback(() => {
    const text = outputLog.map(l => {
      const t = new Date(l.ts * 1000).toLocaleTimeString()
      return `[${t}] [${l.stream}] ${l.text}`
    }).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tars-log-${new Date().toISOString().slice(0, 19)}.log`
    a.click()
    URL.revokeObjectURL(url)
  }, [outputLog])

  const filteredLog = outputLog.filter(l => {
    if (filter === 'all') return true
    if (filter === 'events') return l.stream === 'event' || l.stream === 'system'
    if (filter === 'output') return l.stream === 'stdout'
    if (filter === 'errors') return l.stream === 'stderr'
    return true
  })

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-signal-green" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Live Activity</span>
          {tunnelConnected && (
            <div className="w-1.5 h-1.5 rounded-full bg-signal-green animate-pulse" />
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Filter buttons */}
          <div className="flex items-center gap-px bg-void-800 rounded overflow-hidden">
            {(['all', 'events', 'output', 'errors'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={clsx(
                  'px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider transition-colors',
                  filter === f
                    ? 'bg-panel-border text-star-white'
                    : 'text-slate-600 hover:text-slate-400'
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <button onClick={handleDownload} className="text-slate-600 hover:text-slate-300" title="Download log">
            <Download size={11} />
          </button>
          <button onClick={clearOutput} className="text-slate-600 hover:text-slate-300" title="Clear">
            <Trash2 size={11} />
          </button>
          <span className="text-[10px] text-slate-600">{filteredLog.length}</span>
        </div>
      </div>

      {/* Log output */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden font-mono text-[11px] leading-[18px] bg-void-950 p-1"
      >
        {filteredLog.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-700">
            <Activity size={28} className="mb-2 opacity-30" />
            <p className="text-[10px]">
              {tunnelConnected ? 'Waiting for activity...' : 'Connect tunnel to see live activity'}
            </p>
          </div>
        ) : (
          filteredLog.map((line, i) => {
            const ts = new Date(line.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            return (
              <div
                key={i}
                className={clsx(
                  'flex gap-2 px-1 py-[1px] hover:bg-white/[0.02] animate-fade-in',
                )}
              >
                <span className="text-[10px] text-slate-700 shrink-0 w-[60px] tabular-nums">{ts}</span>
                <span className={clsx(
                  'whitespace-pre-wrap break-all flex-1',
                  line.stream === 'stderr' && 'text-signal-red/90',
                  line.stream === 'system' && 'text-signal-cyan/80',
                  line.stream === 'event' && 'text-slate-200',
                  line.stream === 'stdout' && 'text-slate-400',
                )}>
                  {line.text}
                </span>
              </div>
            )
          })
        )}
      </div>

      {/* Jump to bottom */}
      {!autoScroll && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-2 right-4 z-10 flex items-center gap-1 px-2.5 py-1 rounded-full glass text-[10px] font-semibold text-signal-green border border-signal-green/30 hover:bg-signal-green/10 transition-colors"
        >
          <ChevronDown size={10} />
          Latest
        </button>
      )}
    </div>
  )
}
