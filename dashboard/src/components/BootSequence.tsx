import { useState, useEffect, useCallback } from 'react'
import { useTars } from '../context/ConnectionContext'

const BOOT_STAGES = [
  { label: 'INITIALIZING SUBSYSTEMS', duration: 600 },
  { label: 'ESTABLISHING UPLINK', duration: 800 },
  { label: 'LOADING MEMORY BANKS', duration: 500 },
  { label: 'CALIBRATING AI CORE', duration: 700 },
  { label: 'ALL SYSTEMS NOMINAL', duration: 400 },
]

export default function BootSequence({ onComplete }: { onComplete: () => void }) {
  const { connectionState } = useTars()
  const [stage, setStage] = useState(0)
  const [progress, setProgress] = useState(0)
  const [text, setText] = useState('')
  const [showCursor, setShowCursor] = useState(true)
  const [failed, setFailed] = useState(false)

  // Cursor blink
  useEffect(() => {
    const t = setInterval(() => setShowCursor(c => !c), 500)
    return () => clearInterval(t)
  }, [])

  // Type out text letter by letter
  const typeText = useCallback((fullText: string, cb: () => void) => {
    let i = 0
    setText('')
    const interval = setInterval(() => {
      i++
      setText(fullText.substring(0, i))
      if (i >= fullText.length) {
        clearInterval(interval)
        cb()
      }
    }, 30)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (stage >= BOOT_STAGES.length) {
      setTimeout(onComplete, 600)
      return
    }

    const current = BOOT_STAGES[stage]

    // If we're at stage 1 (ESTABLISHING UPLINK) and disconnected, wait
    const isConnected = connectionState === 'connected'
    if (stage === 1 && !isConnected) {
      const cleanup = typeText('ESTABLISHING UPLINK...', () => {})
      const timeout = setTimeout(() => {
        if (!isConnected) {
          setFailed(true)
        }
      }, 10000)
      return () => { cleanup(); clearTimeout(timeout) }
    }

    // If connection came through while failed, resume
    if (failed && connectionState === 'connected') {
      setFailed(false)
    }

    const cleanup = typeText(current.label, () => {
      // Fill progress
      let p = 0
      const pInterval = setInterval(() => {
        p += 5
        setProgress(((stage * 100) + p) / BOOT_STAGES.length)
        if (p >= 100) {
          clearInterval(pInterval)
          setTimeout(() => setStage(s => s + 1), 150)
        }
      }, current.duration / 20)
    })

    return cleanup
  }, [stage, connectionState, failed, typeText, onComplete])

  // If connected and on uplink stage, advance
  useEffect(() => {
    if (stage === 1 && connectionState === 'connected' && !failed) {
      // Will be handled by main effect
    }
  }, [stage, connectionState, failed])

  return (
    <div className="fixed inset-0 z-[100] bg-void-950 flex flex-col items-center justify-center transition-opacity duration-500">
      {/* TARS ASCII */}
      <pre className="text-signal-cyan text-xs sm:text-sm mb-8 animate-glow select-none leading-tight text-center">
{`████████╗ █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
   ██║   ███████║██████╔╝███████╗
   ██║   ██╔══██║██╔══██╗╚════██║
   ██║   ██║  ██║██║  ██║███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝`}
      </pre>

      <div className="text-xs tracking-[0.3em] text-slate-500 mb-8 uppercase">
        Autonomous Mac Agent // Mission Control v2.0
      </div>

      {/* Stage list */}
      <div className="w-80 space-y-2 mb-6">
        {BOOT_STAGES.map((s, i) => (
          <div key={i} className="flex items-center gap-3 text-xs font-mono">
            <span className={`w-4 text-center ${
              i < stage ? 'text-signal-green' : i === stage ? 'text-signal-cyan' : 'text-slate-700'
            }`}>
              {i < stage ? '+' : i === stage ? '>' : '-'}
            </span>
            <span className={
              i < stage ? 'text-slate-500' : i === stage ? 'text-star-white' : 'text-slate-700'
            }>
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="w-80 h-1 bg-void-700 rounded-full overflow-hidden mb-4">
        <div
          className="h-full bg-gradient-to-r from-signal-cyan to-signal-blue rounded-full transition-all duration-200"
          style={{ width: `${Math.min(100, progress)}%` }}
        />
      </div>

      {/* Current status */}
      <div className="text-xs text-slate-500 h-5 font-mono">
        {failed ? (
          <span className="text-signal-red">UPLINK FAILED -- RETRYING...</span>
        ) : (
          <span>{text}{showCursor ? '_' : ' '}</span>
        )}
      </div>
    </div>
  )
}
