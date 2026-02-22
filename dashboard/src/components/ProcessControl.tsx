import { useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import {
  Power, Square, RotateCcw, Skull,
  Clock, Loader2,
} from 'lucide-react'
import clsx from 'clsx'

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export default function ProcessControl() {
  const {
    connectionState, tunnelConnected, tarsProcess,
    startTars, stopTars, killTars, restartTars,
  } = useTars()
  const [showKillConfirm, setShowKillConfirm] = useState(false)

  const isConnected = connectionState === 'connected'
  const isRunning = tarsProcess.running && tarsProcess.status === 'running'
  const isStarting = tarsProcess.status === 'starting'
  const isStopping = tarsProcess.status === 'stopping'
  const isBusy = isStarting || isStopping

  const handleStart = useCallback(() => {
    startTars()
  }, [startTars])

  const handleKill = useCallback(() => {
    if (!showKillConfirm) {
      setShowKillConfirm(true)
      setTimeout(() => setShowKillConfirm(false), 5000)
      return
    }
    killTars()
    setShowKillConfirm(false)
  }, [killTars, showKillConfirm])

  const statusColor = isRunning ? 'text-signal-green'
    : isStarting ? 'text-signal-amber'
    : isStopping ? 'text-signal-amber'
    : tarsProcess.status === 'error' ? 'text-signal-red'
    : 'text-slate-500'

  const statusDot = isRunning ? 'bg-signal-green shadow-[0_0_6px_rgba(16,185,129,0.5)]'
    : isStarting ? 'bg-signal-amber animate-pulse'
    : isStopping ? 'bg-signal-amber animate-pulse'
    : tarsProcess.status === 'error' ? 'bg-signal-red'
    : 'bg-slate-600'

  return (
    <div className="p-3 space-y-3">
      {/* TARS Status — compact block */}
      <div className={clsx(
        'rounded-xl border p-3',
        isRunning ? 'border-signal-green/20 bg-signal-green/[0.03]' : 'border-panel-border bg-panel-surface/20'
      )}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className={clsx('w-2.5 h-2.5 rounded-full', statusDot)} />
            <div>
              <div className={clsx('text-xs font-bold uppercase tracking-wider', statusColor)}>
                {tarsProcess.status}
              </div>
              {tarsProcess.pid && (
                <div className="text-[9px] text-slate-600">PID {tarsProcess.pid}</div>
              )}
            </div>
          </div>
          {isRunning && tarsProcess.uptime > 0 && (
            <div className="flex items-center gap-1 text-[10px] text-slate-500">
              <Clock size={9} />
              {formatUptime(tarsProcess.uptime)}
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      {!isRunning && !isBusy && (
        <button
          onClick={handleStart}
          disabled={!tunnelConnected}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-widest bg-signal-green/15 text-signal-green border border-signal-green/25 hover:bg-signal-green/25 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Power size={13} />
          Start TARS
        </button>
      )}

      {isStarting && (
        <div className="flex items-center justify-center gap-2 py-2.5 text-signal-amber">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-[10px] font-semibold uppercase tracking-wider">Starting...</span>
        </div>
      )}

      {isStopping && (
        <div className="flex items-center justify-center gap-2 py-2.5 text-signal-amber">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-[10px] font-semibold uppercase tracking-wider">Stopping...</span>
        </div>
      )}

      {isRunning && (
        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={stopTars}
            className="flex items-center justify-center gap-1 py-2 rounded-lg text-[9px] font-bold uppercase tracking-wider bg-signal-amber/10 text-signal-amber border border-signal-amber/20 hover:bg-signal-amber/20 transition-all"
          >
            <Square size={9} />
            Stop
          </button>
          <button
            onClick={() => restartTars()}
            className="flex items-center justify-center gap-1 py-2 rounded-lg text-[9px] font-bold uppercase tracking-wider bg-signal-blue/10 text-signal-blue border border-signal-blue/20 hover:bg-signal-blue/20 transition-all"
          >
            <RotateCcw size={9} />
            Restart
          </button>
          <button
            onClick={handleKill}
            className={clsx(
              'flex items-center justify-center gap-1 py-2 rounded-lg text-[9px] font-bold uppercase tracking-wider border transition-all',
              showKillConfirm
                ? 'bg-signal-red/30 text-signal-red border-signal-red animate-pulse'
                : 'bg-signal-red/10 text-signal-red border-signal-red/20 hover:bg-signal-red/20'
            )}
          >
            <Skull size={9} />
            {showKillConfirm ? 'Confirm!' : 'Kill'}
          </button>
        </div>
      )}
    </div>
  )
}
