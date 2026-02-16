import { useTars } from '../context/ConnectionContext'
import { Activity, CheckCircle2, XCircle, Clock, Wrench } from 'lucide-react'
import clsx from 'clsx'

export default function ActionLog() {
  const { actionLog } = useTars()

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-signal-amber" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Action Log</span>
        </div>
        <span className="text-[10px] text-slate-600">{actionLog.length}</span>
      </div>

      {/* Table header */}
      <div className="grid grid-cols-[60px_110px_1fr_40px_50px] gap-1 px-3 py-1.5 border-b border-panel-border text-[9px] font-bold uppercase tracking-widest text-slate-600 bg-panel-surface/30 shrink-0">
        <div>Time</div>
        <div>Tool</div>
        <div>Details</div>
        <div className="text-center">OK</div>
        <div className="text-right">Dur</div>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        {actionLog.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-700 text-[10px]">
            No actions recorded
          </div>
        ) : (
          actionLog.map(entry => (
            <div
              key={entry.id}
              className="grid grid-cols-[60px_110px_1fr_40px_50px] gap-1 px-3 py-1.5 border-b border-panel-border/50 text-[11px] hover:bg-white/[0.01] transition-colors animate-fade-in"
            >
              <div className="text-slate-600 text-[10px] truncate">{entry.time}</div>
              <div className="flex items-center gap-1 text-thrust font-semibold truncate">
                <Wrench size={10} className="shrink-0" />
                {entry.toolName}
              </div>
              <div className="text-slate-400 truncate" title={entry.detail}>{entry.detail}</div>
              <div className="flex justify-center">
                {entry.success ? (
                  <CheckCircle2 size={11} className="text-signal-green" />
                ) : (
                  <XCircle size={11} className="text-signal-red" />
                )}
              </div>
              <div className="text-right text-slate-600 text-[10px]">
                {entry.duration != null ? `${entry.duration.toFixed(1)}s` : '--'}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
