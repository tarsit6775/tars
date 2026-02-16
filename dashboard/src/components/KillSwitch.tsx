import { useState, useCallback } from 'react'
import { ShieldAlert, ShieldOff, Power, Square } from 'lucide-react'
import { useTars } from '../context/ConnectionContext'
import clsx from 'clsx'

export default function KillSwitch() {
  const { killTars, stopTars, tarsProcess, tunnelConnected } = useTars()
  const [armed, setArmed] = useState(false)

  const handleClick = useCallback(() => {
    if (!armed) {
      setArmed(true)
      // Auto-disarm after 5 seconds
      setTimeout(() => setArmed(false), 5000)
    } else {
      killTars()
      setArmed(false)
    }
  }, [armed, killTars])

  if (!tunnelConnected) {
    return (
      <button
        disabled
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-[10px] font-bold uppercase tracking-widest bg-slate-800/50 text-slate-600 border border-slate-700 cursor-not-allowed"
      >
        <Power size={12} />
        OFFLINE
      </button>
    )
  }

  if (!tarsProcess.running) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded text-[10px] font-bold uppercase tracking-widest bg-void-800/50 text-slate-500 border border-panel-border">
        <Square size={10} className="text-slate-600" />
        STOPPED
      </div>
    )
  }

  return (
    <button
      onClick={handleClick}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded text-[10px] font-bold uppercase tracking-widest transition-all duration-200',
        armed
          ? 'bg-signal-red/30 text-signal-red border border-signal-red shadow-glow-red animate-pulse'
          : 'bg-signal-red/10 text-signal-red/70 border border-signal-red/30 hover:bg-signal-red/20 hover:border-signal-red/50'
      )}
    >
      <ShieldAlert size={12} />
      {armed ? 'CONFIRM KILL' : 'KILL'}
    </button>
  )
}
