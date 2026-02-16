import { useState, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'
import {
  Power, Square, RotateCcw, Skull, Wifi, WifiOff, Monitor, Cpu,
  Play, Clock, Zap, AlertTriangle, Loader2,
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
  const [startTask, setStartTask] = useState('')
  const [showKillConfirm, setShowKillConfirm] = useState(false)

  const isConnected = connectionState === 'connected'
  const isRunning = tarsProcess.running && tarsProcess.status === 'running'
  const isStarting = tarsProcess.status === 'starting'
  const isStopping = tarsProcess.status === 'stopping'
  const isBusy = isStarting || isStopping

  const handleStart = useCallback(() => {
    startTars(startTask.trim() || undefined)
    setStartTask('')
  }, [startTars, startTask])

  const handleKill = useCallback(() => {
    if (!showKillConfirm) {
      setShowKillConfirm(true)
      setTimeout(() => setShowKillConfirm(false), 5000)
      return
    }
    killTars()
    setShowKillConfirm(false)
  }, [killTars, showKillConfirm])

  // Status indicator
  const statusColor = isRunning
    ? 'text-signal-green'
    : isStarting ? 'text-signal-amber'
    : isStopping ? 'text-signal-amber'
    : tarsProcess.status === 'error' ? 'text-signal-red'
    : 'text-slate-500'

  const statusDot = isRunning
    ? 'bg-signal-green shadow-glow-green'
    : isStarting ? 'bg-signal-amber animate-pulse'
    : isStopping ? 'bg-signal-amber animate-pulse'
    : tarsProcess.status === 'error' ? 'bg-signal-red'
    : 'bg-slate-600'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
        <div className="flex items-center gap-2">
          <Cpu size={13} className="text-signal-cyan" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Process Control
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Connection Status */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
            Connection
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg border',
              isConnected
                ? 'bg-signal-green/5 border-signal-green/20'
                : 'bg-signal-red/5 border-signal-red/20'
            )}>
              {isConnected ? <Wifi size={14} className="text-signal-green" /> : <WifiOff size={14} className="text-signal-red" />}
              <div>
                <div className={clsx('text-[11px] font-semibold', isConnected ? 'text-signal-green' : 'text-signal-red')}>
                  Relay
                </div>
                <div className="text-[9px] text-slate-600">{isConnected ? 'Connected' : 'Disconnected'}</div>
              </div>
            </div>
            <div className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg border',
              tunnelConnected
                ? 'bg-signal-green/5 border-signal-green/20'
                : 'bg-signal-red/5 border-signal-red/20'
            )}>
              <Monitor size={14} className={tunnelConnected ? 'text-signal-green' : 'text-signal-red'} />
              <div>
                <div className={clsx('text-[11px] font-semibold', tunnelConnected ? 'text-signal-green' : 'text-signal-red')}>
                  Mac Tunnel
                </div>
                <div className="text-[9px] text-slate-600">{tunnelConnected ? 'Online' : 'Offline'}</div>
              </div>
            </div>
          </div>
        </div>

        {/* TARS Process Status */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
            TARS Agent
          </div>
          <div className={clsx(
            'rounded-xl border p-4 space-y-3',
            isRunning ? 'border-signal-green/30 bg-signal-green/5' : 'border-panel-border bg-panel-surface/30'
          )}>
            {/* Status row */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={clsx('w-3 h-3 rounded-full', statusDot)} />
                <div>
                  <div className={clsx('text-sm font-bold uppercase tracking-wider', statusColor)}>
                    {tarsProcess.status}
                  </div>
                  {tarsProcess.pid && (
                    <div className="text-[10px] text-slate-600">PID {tarsProcess.pid}</div>
                  )}
                </div>
              </div>
              {isRunning && tarsProcess.uptime > 0 && (
                <div className="flex items-center gap-1 text-[10px] text-slate-500">
                  <Clock size={10} />
                  {formatUptime(tarsProcess.uptime)}
                </div>
              )}
            </div>

            {/* Not connected warning */}
            {!tunnelConnected && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-signal-amber/10 border border-signal-amber/20">
                <AlertTriangle size={14} className="text-signal-amber shrink-0" />
                <div className="text-[11px] text-signal-amber">
                  Mac tunnel offline. Start <code className="text-[10px] bg-void-800 px-1 py-0.5 rounded">tunnel.py</code> on your Mac.
                </div>
              </div>
            )}

            {/* Start task input + button */}
            {!isRunning && !isBusy && tunnelConnected && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={startTask}
                  onChange={(e) => setStartTask(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleStart()}
                  placeholder="Optional: initial task..."
                  className="w-full bg-void-800 border border-panel-border rounded-lg px-3 py-2 text-xs text-star-white placeholder-slate-600 outline-none focus:border-signal-green/50 transition-colors"
                />
                <button
                  onClick={handleStart}
                  disabled={!tunnelConnected}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold uppercase tracking-widest bg-signal-green/20 text-signal-green border border-signal-green/30 hover:bg-signal-green/30 hover:shadow-glow-green transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <Power size={14} />
                  Start TARS
                </button>
              </div>
            )}

            {/* Starting spinner */}
            {isStarting && (
              <div className="flex items-center justify-center gap-2 py-3 text-signal-amber">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-xs font-semibold uppercase tracking-wider">Starting...</span>
              </div>
            )}

            {/* Control buttons when running */}
            {isRunning && (
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={stopTars}
                  className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-signal-amber/10 text-signal-amber border border-signal-amber/30 hover:bg-signal-amber/20 transition-all"
                >
                  <Square size={10} />
                  Stop
                </button>
                <button
                  onClick={() => restartTars()}
                  className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-signal-blue/10 text-signal-blue border border-signal-blue/30 hover:bg-signal-blue/20 transition-all"
                >
                  <RotateCcw size={10} />
                  Restart
                </button>
                <button
                  onClick={handleKill}
                  className={clsx(
                    'flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider border transition-all',
                    showKillConfirm
                      ? 'bg-signal-red/30 text-signal-red border-signal-red shadow-glow-red animate-pulse'
                      : 'bg-signal-red/10 text-signal-red border-signal-red/30 hover:bg-signal-red/20'
                  )}
                >
                  <Skull size={10} />
                  {showKillConfirm ? 'Confirm!' : 'Kill'}
                </button>
              </div>
            )}

            {/* Stopping */}
            {isStopping && (
              <div className="flex items-center justify-center gap-2 py-3 text-signal-amber">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-xs font-semibold uppercase tracking-wider">Stopping...</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
