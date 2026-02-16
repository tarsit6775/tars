import { useState, useEffect, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import { Database, FileText, Save, RefreshCw, Clock, Search, CheckCircle2, XCircle } from 'lucide-react'
import clsx from 'clsx'

export default function MemoryPage() {
  const { memoryContext, memoryPreferences, actionLog, saveMemory, requestMemory } = useTars()
  const [tab, setTab] = useState<'context' | 'preferences' | 'history'>('context')
  const [editContext, setEditContext] = useState('')
  const [editPrefs, setEditPrefs] = useState('')
  const [historyFilter, setHistoryFilter] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => { setEditContext(memoryContext) }, [memoryContext])
  useEffect(() => { setEditPrefs(memoryPreferences) }, [memoryPreferences])
  useEffect(() => { requestMemory() }, [requestMemory])

  const handleSave = useCallback((field: string) => {
    const content = field === 'context' ? editContext : editPrefs
    saveMemory(field, content)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }, [editContext, editPrefs, saveMemory])

  const filteredLog = historyFilter
    ? actionLog.filter(a =>
        a.toolName.toLowerCase().includes(historyFilter.toLowerCase()) ||
        a.detail.toLowerCase().includes(historyFilter.toLowerCase())
      )
    : actionLog

  return (
    <div className="h-full flex flex-col">
      {/* Tabs */}
      <div className="flex items-center border-b border-panel-border shrink-0">
        {[
          { id: 'context' as const, label: 'Context', icon: <FileText size={11} /> },
          { id: 'preferences' as const, label: 'Preferences', icon: <Database size={11} /> },
          { id: 'history' as const, label: 'History', icon: <Clock size={11} /> },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2.5 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2',
              tab === t.id
                ? 'text-signal-cyan border-signal-cyan bg-signal-cyan/5'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            )}
          >
            {t.icon} {t.label}
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={requestMemory}
          className="px-3 py-1.5 mr-2 text-[10px] text-slate-500 hover:text-signal-cyan transition-colors"
          title="Refresh"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'context' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Current Context</h3>
              <button
                onClick={() => handleSave('context')}
                className={clsx(
                  'flex items-center gap-1 px-3 py-1 rounded text-[10px] font-bold transition-all',
                  saved ? 'bg-signal-green/20 text-signal-green' : 'bg-signal-blue/20 text-signal-blue hover:bg-signal-blue/30'
                )}
              >
                <Save size={10} /> {saved ? 'Saved' : 'Save'}
              </button>
            </div>
            <textarea
              value={editContext}
              onChange={(e) => setEditContext(e.target.value)}
              className="w-full h-[calc(100vh-220px)] bg-void-800 border border-panel-border rounded-lg p-3 text-xs text-slate-300 font-mono resize-none outline-none focus:border-signal-cyan/50 leading-relaxed"
              spellCheck={false}
            />
          </div>
        )}

        {tab === 'preferences' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Preferences</h3>
              <button
                onClick={() => handleSave('preferences')}
                className={clsx(
                  'flex items-center gap-1 px-3 py-1 rounded text-[10px] font-bold transition-all',
                  saved ? 'bg-signal-green/20 text-signal-green' : 'bg-signal-blue/20 text-signal-blue hover:bg-signal-blue/30'
                )}
              >
                <Save size={10} /> {saved ? 'Saved' : 'Save'}
              </button>
            </div>
            <textarea
              value={editPrefs}
              onChange={(e) => setEditPrefs(e.target.value)}
              className="w-full h-[calc(100vh-220px)] bg-void-800 border border-panel-border rounded-lg p-3 text-xs text-slate-300 font-mono resize-none outline-none focus:border-signal-cyan/50 leading-relaxed"
              spellCheck={false}
            />
          </div>
        )}

        {tab === 'history' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-1.5 bg-void-800 border border-panel-border rounded px-2.5 py-1.5">
                <Search size={11} className="text-slate-600" />
                <input
                  type="text"
                  value={historyFilter}
                  onChange={(e) => setHistoryFilter(e.target.value)}
                  placeholder="Filter history..."
                  className="flex-1 bg-transparent text-xs text-star-white placeholder-slate-600 outline-none"
                />
              </div>
              <span className="text-[10px] text-slate-600">{filteredLog.length} entries</span>
            </div>

            <div className="space-y-1">
              {filteredLog.slice().reverse().map(entry => (
                <div key={entry.id} className="flex items-start gap-2 px-3 py-2 rounded-lg bg-void-800 border border-panel-border/50 hover:border-panel-border transition-colors">
                  <div className="mt-0.5 shrink-0">
                    {entry.success ? <CheckCircle2 size={11} className="text-signal-green" /> : <XCircle size={11} className="text-signal-red" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-semibold text-thrust">{entry.toolName}</span>
                      <span className="text-[9px] text-slate-600">{entry.time}</span>
                      {entry.duration != null && <span className="text-[9px] text-slate-600">{entry.duration.toFixed(1)}s</span>}
                    </div>
                    <p className="text-[11px] text-slate-400 truncate mt-0.5">{entry.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
