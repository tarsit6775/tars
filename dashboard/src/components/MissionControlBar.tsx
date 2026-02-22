import { useState, useEffect } from 'react'
import { useTars } from '../context/ConnectionContext'
import StatusHUD from './StatusHUD'
import { Clock, Cpu, DollarSign, BarChart3 } from 'lucide-react'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

interface MissionControlBarProps {
  activeView: string
  onViewChange: (view: string) => void
}

export default function MissionControlBar({ activeView, onViewChange }: MissionControlBarProps) {
  const { stats, currentModel, actionLog } = useTars()
  const [uptime, setUptime] = useState(0)

  useEffect(() => {
    const start = Date.now()
    const t = setInterval(() => setUptime((Date.now() - start) / 1000), 1000)
    return () => clearInterval(t)
  }, [])

  const views = [
    { id: 'dashboard', label: 'CONTROL' },
    { id: 'email', label: 'EMAIL' },
    { id: 'analytics', label: 'ANALYTICS' },
    { id: 'memory', label: 'MEMORY' },
    { id: 'settings', label: 'SETTINGS' },
  ]

  return (
    <header className="relative z-20 glass-heavy flex items-center h-11 px-4 gap-3 select-none" role="banner">
      {/* Logo */}
      <div className="flex items-center gap-3 mr-1">
        <h1 className="text-base font-extrabold tracking-[0.25em] text-gradient">TARS</h1>
        <div className="hidden md:block h-4 w-px bg-panel-border" />
      </div>

      {/* Nav tabs */}
      <nav className="hidden md:flex items-center gap-0.5 mr-auto">
        {views.map(v => (
          <button
            key={v.id}
            onClick={() => onViewChange(v.id)}
            className={`px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-widest transition-all ${
              activeView === v.id
                ? 'text-signal-cyan bg-signal-cyan/10 border border-signal-cyan/30'
                : 'text-slate-500 hover:text-slate-300 border border-transparent'
            }`}
          >
            {v.label}
          </button>
        ))}
      </nav>

      {/* Status HUD — center/right */}
      <div className="hidden md:flex items-center">
        <StatusHUD />
      </div>

      {/* Metrics — far right */}
      <div className="hidden lg:flex items-center gap-3 text-[10px] text-slate-500 ml-3">
        <div className="flex items-center gap-1" title="Uptime">
          <Clock size={10} className="text-slate-600" />
          <span className="text-star-white font-semibold tabular-nums">{formatUptime(stats.uptime_seconds || uptime)}</span>
        </div>
        <div className="flex items-center gap-1" title="Cost">
          <DollarSign size={10} className="text-slate-600" />
          <span className="text-star-white font-semibold">{(stats.total_cost || 0).toFixed(3)}</span>
        </div>
        <div className="flex items-center gap-1" title="Tokens">
          <BarChart3 size={10} className="text-slate-600" />
          <span className="text-star-white font-semibold">{formatNumber((stats.total_tokens_in || 0) + (stats.total_tokens_out || 0))}</span>
        </div>
      </div>

      {/* Connection indicator line */}
      {/* (connectionState checked via StatusHUD now) */}
    </header>
  )
}
