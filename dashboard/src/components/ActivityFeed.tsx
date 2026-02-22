import { useRef, useEffect, useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import {
    ChevronDown, Search, Wrench, CheckCircle2, XCircle,
    Brain, Zap, Download, Trash2, Filter,
} from 'lucide-react'
import clsx from 'clsx'

type FeedFilter = 'all' | 'thinking' | 'tools' | 'errors'

// Merge ThinkingBlocks + OutputLog into a single timeline
interface FeedItem {
    id: string
    type: 'thinking' | 'tool_call' | 'tool_result' | 'error' | 'system' | 'output'
    ts: number
    // Thinking
    model?: string
    text?: string
    // Tool
    toolName?: string
    toolInput?: any
    content?: string
    success?: boolean
    duration?: number
    time?: string
}

function ModelBadge({ model }: { model: string }) {
    const label = model.includes('haiku') ? 'HAIKU'
        : model.includes('sonnet') ? 'SONNET'
        : model.includes('gemini') ? 'GEMINI'
        : model.includes('llama') ? 'LLAMA'
        : model.includes('gpt') ? 'GPT'
        : model.toUpperCase().slice(0, 8)
    const isSmall = model.includes('haiku') || model.includes('llama') || model.includes('flash')
    return (
        <span className={clsx(
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider',
            isSmall
                ? 'bg-signal-purple/15 text-signal-purple/80 border border-signal-purple/20'
                : 'bg-signal-cyan/15 text-signal-cyan/80 border border-signal-cyan/20'
        )}>
            {isSmall ? <Zap size={8} /> : <Brain size={8} />}
            {label}
        </span>
    )
}

function ToolBlock({ item }: { item: FeedItem }) {
    const [expanded, setExpanded] = useState(false)
    const isResult = item.type === 'tool_result'

    return (
        <div className={clsx(
            'rounded-lg border overflow-hidden animate-fade-in',
            isResult
                ? item.success
                    ? 'border-signal-green/20 bg-signal-green/[0.03]'
                    : 'border-signal-red/20 bg-signal-red/[0.03]'
                : 'border-panel-border bg-panel-surface/40'
        )}>
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium hover:bg-white/[0.02] transition-colors"
            >
                {isResult ? (
                    item.success
                        ? <CheckCircle2 size={11} className="text-signal-green shrink-0" />
                        : <XCircle size={11} className="text-signal-red shrink-0" />
                ) : (
                    <Wrench size={11} className="text-thrust shrink-0" />
                )}
                <span className={clsx(
                    'font-semibold',
                    isResult ? (item.success ? 'text-signal-green' : 'text-signal-red') : 'text-thrust'
                )}>
                    {item.toolName}
                </span>
                {item.duration != null && (
                    <span className="text-[10px] text-slate-600 ml-auto mr-2">{item.duration.toFixed(1)}s</span>
                )}
                <ChevronDown size={10} className={clsx(
                    'text-slate-600 transition-transform shrink-0',
                    expanded && 'rotate-180'
                )} />
            </button>
            {expanded && (
                <div className="px-3 py-2 border-t border-panel-border/50 text-[11px] text-slate-400 font-mono whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                    {isResult ? String(item.content || '').substring(0, 2000) : JSON.stringify(item.toolInput, null, 2)}
                </div>
            )}
        </div>
    )
}

export default function ActivityFeed() {
    const { thinkingBlocks, outputLog, clearOutput } = useTars()
    const containerRef = useRef<HTMLDivElement>(null)
    const [autoScroll, setAutoScroll] = useState(true)
    const [filter, setFilter] = useState<FeedFilter>('all')
    const [searchText, setSearchText] = useState('')
    const [showSearch, setShowSearch] = useState(false)

    // Auto-scroll
    useEffect(() => {
        if (autoScroll && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight
        }
    }, [thinkingBlocks, outputLog, autoScroll])

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
        const lines: string[] = []
        thinkingBlocks.forEach(b => {
            if (b.type === 'thinking') lines.push(`[THINK] ${b.text}`)
            if (b.type === 'tool_call') lines.push(`[TOOL] ${b.toolName}: ${JSON.stringify(b.toolInput)}`)
            if (b.type === 'tool_result') lines.push(`[RESULT] ${b.toolName}: ${b.success ? '✓' : '✗'} ${b.content}`)
            if (b.type === 'error') lines.push(`[ERROR] ${b.text}`)
        })
        outputLog.forEach(l => {
            const ts = new Date(l.ts * 1000).toISOString()
            lines.push(`[${ts}] [${l.stream}] ${l.text}`)
        })
        const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `tars-activity-${new Date().toISOString().slice(0, 19)}.log`
        a.click()
        URL.revokeObjectURL(url)
    }, [thinkingBlocks, outputLog])

    // Build unified feed from thinkingBlocks (primary) with system messages interleaved
    const feed: FeedItem[] = []

    // Add thinking blocks as primary content
    thinkingBlocks.forEach(block => {
        feed.push({
            id: block.id,
            type: block.type,
            ts: block.time ? new Date().getTime() : Date.now(),
            model: block.model,
            text: block.text,
            toolName: block.toolName,
            toolInput: block.toolInput,
            content: block.content,
            success: block.success,
            duration: block.duration,
            time: block.time,
        })
    })

    // Add system/error output lines that aren't duplicated in thinking blocks
    outputLog.forEach((line, i) => {
        if (line.stream === 'system') {
            feed.push({
                id: `sys-${i}`,
                type: 'system',
                ts: line.ts * 1000,
                text: line.text,
            })
        } else if (line.stream === 'stderr') {
            feed.push({
                id: `err-${i}`,
                type: 'error',
                ts: line.ts * 1000,
                text: line.text,
            })
        }
    })

    // Apply filter
    const filtered = feed.filter(item => {
        if (filter === 'thinking' && item.type !== 'thinking') return false
        if (filter === 'tools' && item.type !== 'tool_call' && item.type !== 'tool_result') return false
        if (filter === 'errors' && item.type !== 'error') return false
        if (searchText) {
            const text = (item.text || '') + (item.toolName || '') + (item.content || '')
            if (!text.toLowerCase().includes(searchText.toLowerCase())) return false
        }
        return true
    })

    const isEmpty = filtered.length === 0
    const thinkingCount = feed.filter(f => f.type === 'thinking').length
    const toolCount = feed.filter(f => f.type === 'tool_call' || f.type === 'tool_result').length

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-panel-border bg-panel-surface/30 shrink-0">
                <div className="flex items-center gap-3">
                    <Brain size={14} className="text-signal-cyan" />
                    <span className="text-[11px] font-bold uppercase tracking-widest text-slate-300">Activity</span>
                    {/* Quick counts */}
                    <div className="flex items-center gap-2 text-[10px] text-slate-600">
                        {thinkingCount > 0 && <span>{thinkingCount} thoughts</span>}
                        {toolCount > 0 && <span>• {toolCount} tools</span>}
                    </div>
                </div>
                <div className="flex items-center gap-1.5">
                    {/* Filter pills */}
                    <div className="flex items-center gap-px bg-void-800 rounded-lg overflow-hidden border border-panel-border/50">
                        {(['all', 'thinking', 'tools', 'errors'] as const).map(f => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                className={clsx(
                                    'px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider transition-colors',
                                    filter === f
                                        ? 'bg-signal-cyan/15 text-signal-cyan'
                                        : 'text-slate-600 hover:text-slate-400'
                                )}
                            >
                                {f}
                            </button>
                        ))}
                    </div>
                    <button onClick={() => setShowSearch(!showSearch)} className="p-1 text-slate-600 hover:text-slate-300 transition-colors" title="Search">
                        <Search size={12} />
                    </button>
                    <button onClick={handleDownload} className="p-1 text-slate-600 hover:text-slate-300 transition-colors" title="Download">
                        <Download size={12} />
                    </button>
                    <button onClick={clearOutput} className="p-1 text-slate-600 hover:text-slate-300 transition-colors" title="Clear">
                        <Trash2 size={12} />
                    </button>
                </div>
            </div>

            {/* Search bar */}
            {showSearch && (
                <div className="px-4 py-2 border-b border-panel-border/50 shrink-0">
                    <input
                        type="text"
                        value={searchText}
                        onChange={(e) => setSearchText(e.target.value)}
                        placeholder="Search activity..."
                        autoFocus
                        className="w-full bg-void-800 border border-panel-border rounded-lg px-3 py-1.5 text-xs text-star-white placeholder-slate-600 outline-none focus:border-signal-cyan/40"
                    />
                </div>
            )}

            {/* Unified feed */}
            <div
                ref={containerRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto p-4 space-y-2"
            >
                {isEmpty ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-600">
                        <Brain size={36} className="mb-3 opacity-20" />
                        <p className="text-xs font-medium">Waiting for TARS...</p>
                        <p className="text-[10px] text-slate-700 mt-1">Activity will appear here when TARS starts working</p>
                    </div>
                ) : (
                    filtered.map((item) => {
                        // Thinking block
                        if (item.type === 'thinking') {
                            return (
                                <div key={item.id} className="animate-fade-in">
                                    <div className="flex items-center gap-2 mb-1">
                                        {item.model && <ModelBadge model={item.model} />}
                                        {item.time && <span className="text-[9px] text-slate-700">{item.time}</span>}
                                    </div>
                                    <div className="text-[13px] leading-relaxed text-slate-200 whitespace-pre-wrap break-words pl-1">
                                        {item.text}
                                    </div>
                                </div>
                            )
                        }

                        // Tool call or result
                        if (item.type === 'tool_call' || item.type === 'tool_result') {
                            return <ToolBlock key={item.id} item={item} />
                        }

                        // System message
                        if (item.type === 'system') {
                            return (
                                <div key={item.id} className="text-[11px] text-signal-cyan/60 pl-1 animate-fade-in">
                                    {item.text}
                                </div>
                            )
                        }

                        // Error
                        if (item.type === 'error') {
                            return (
                                <div key={item.id} className="flex items-start gap-2 p-2 rounded-lg bg-signal-red/5 border border-signal-red/20 animate-fade-in">
                                    <XCircle size={12} className="text-signal-red mt-0.5 shrink-0" />
                                    <span className="text-[11px] text-signal-red/90">{item.text}</span>
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
                    className="absolute bottom-3 right-4 z-10 flex items-center gap-1 px-3 py-1.5 rounded-full glass text-[10px] font-semibold text-signal-cyan border border-signal-cyan/30 hover:bg-signal-cyan/10 transition-colors shadow-lg"
                >
                    <ChevronDown size={10} />
                    Latest
                </button>
            )}
        </div>
    )
}
