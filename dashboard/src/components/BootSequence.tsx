import { useState, useEffect, useCallback, useRef } from 'react'
import { useTars } from '../context/ConnectionContext'

const FALLBACK_STAGES = [
  'CONNECTING TO TARS',
  'WAITING FOR INIT DATA',
]

export default function BootSequence({ onComplete }: { onComplete: () => void }) {
  const { connectionState, initData } = useTars()
  const [showCursor, setShowCursor] = useState(true)
  const [revealedSteps, setRevealedSteps] = useState(0)
  const [envRevealed, setEnvRevealed] = useState(false)
  const [fallbackStage, setFallbackStage] = useState(0)
  const completedRef = useRef(false)

  // Cursor blink
  useEffect(() => {
    const t = setInterval(() => setShowCursor(c => !c), 500)
    return () => clearInterval(t)
  }, [])

  // Fallback: cycle "CONNECTING..." until we get real data
  useEffect(() => {
    if (initData) return
    if (connectionState === 'connected' && fallbackStage === 0) {
      setFallbackStage(1)
    }
    if (connectionState !== 'connected' && fallbackStage === 0) {
      const t = setTimeout(() => setFallbackStage(0), 2000)
      return () => clearTimeout(t)
    }
  }, [connectionState, initData, fallbackStage])

  // When initData arrives, reveal steps one by one
  useEffect(() => {
    if (!initData || completedRef.current) return
    const steps = initData.steps || []
    if (revealedSteps >= steps.length) {
      // All steps revealed, show env then complete
      if (!envRevealed) {
        const t = setTimeout(() => setEnvRevealed(true), 300)
        return () => clearTimeout(t)
      }
      const t = setTimeout(() => {
        completedRef.current = true
        onComplete()
      }, 800)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setRevealedSteps(r => r + 1), 120)
    return () => clearTimeout(t)
  }, [initData, revealedSteps, envRevealed, onComplete])

  // If connected and TARS already running (no init event in history),
  // skip boot after a short delay
  useEffect(() => {
    if (connectionState !== 'connected' || initData || completedRef.current) return
    const t = setTimeout(() => {
      if (!initData && !completedRef.current) {
        completedRef.current = true
        onComplete()
      }
    }, 5000)
    return () => clearTimeout(t)
  }, [connectionState, initData, onComplete])

  const steps = initData?.steps || []
  const env = initData?.environment
  const totalSteps = steps.length
  const progress = totalSteps > 0 ? (revealedSteps / totalSteps) * 100 : 0

  return (
    <div className="fixed inset-0 z-[100] bg-void-950 flex flex-col items-center justify-center transition-opacity duration-500">
      {/* TARS ASCII */}
      <pre className="text-signal-cyan text-xs sm:text-sm mb-6 animate-glow select-none leading-tight text-center">
{`████████╗ █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
   ██║   ███████║██████╔╝███████╗
   ██║   ██╔══██║██╔══██╗╚════██║
   ██║   ██║  ██║██║  ██║███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝`}
      </pre>

      <div className="text-xs tracking-[0.3em] text-slate-500 mb-6 uppercase">
        {initData
          ? `Autonomous Mac Agent // v${initData.version}`
          : 'Autonomous Mac Agent // Connecting...'}
      </div>

      {/* Init steps — real or fallback */}
      <div className="w-96 max-w-[90vw] space-y-1 mb-4 max-h-[40vh] overflow-y-auto scrollbar-thin">
        {!initData ? (
          /* Fallback stages while waiting */
          FALLBACK_STAGES.slice(0, fallbackStage + 1).map((label, i) => (
            <div key={i} className="flex items-center gap-3 text-xs font-mono">
              <span className={`w-4 text-center ${
                i < fallbackStage ? 'text-signal-green' : 'text-signal-cyan animate-pulse'
              }`}>
                {i < fallbackStage ? '✓' : '▸'}
              </span>
              <span className={i < fallbackStage ? 'text-slate-500' : 'text-star-white'}>
                {label}
              </span>
            </div>
          ))
        ) : (
          /* Real init steps */
          steps.slice(0, revealedSteps).map((step, i) => (
            <div key={i} className="flex items-center gap-3 text-xs font-mono">
              <span className={`w-4 text-center ${
                step.status === 'ok' ? 'text-signal-green'
                  : step.status === 'skip' ? 'text-yellow-500'
                  : 'text-signal-red'
              }`}>
                {step.status === 'ok' ? '✓' : step.status === 'skip' ? '–' : '✗'}
              </span>
              <span className="text-slate-400 w-28 shrink-0 truncate">{step.label}</span>
              <span className="text-slate-600 truncate">{step.detail}</span>
            </div>
          ))
        )}
      </div>

      {/* Progress bar */}
      <div className="w-96 max-w-[90vw] h-1 bg-void-700 rounded-full overflow-hidden mb-4">
        <div
          className="h-full bg-gradient-to-r from-signal-cyan to-signal-blue rounded-full transition-all duration-200"
          style={{ width: `${Math.min(100, progress)}%` }}
        />
      </div>

      {/* Environment snapshot */}
      {envRevealed && env && (
        <div className="w-96 max-w-[90vw] grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono text-slate-500 mb-4 animate-fade-in">
          {env.battery && (
            <div>🔋 Battery: <span className="text-slate-300">{env.battery}</span></div>
          )}
          {env.wifi && (
            <div>📶 WiFi: <span className="text-slate-300">{env.wifi}</span></div>
          )}
          {env.disk_free && (
            <div>💾 Disk: <span className="text-slate-300">{env.disk_free}</span></div>
          )}
          {env.volume !== undefined && (
            <div>🔊 Volume: <span className="text-slate-300">{env.volume}%</span></div>
          )}
          {env.running_apps && env.running_apps.length > 0 && (
            <div className="col-span-2">
              🖥️ Apps: <span className="text-slate-300">{env.running_apps.length} running</span>
              <span className="text-slate-600"> ({env.running_apps.slice(0, 5).join(', ')}{env.running_apps.length > 5 ? '…' : ''})</span>
            </div>
          )}
        </div>
      )}

      {/* LLM info */}
      {envRevealed && initData && (
        <div className="flex gap-6 text-xs font-mono text-slate-600 mb-4">
          <div>🧠 Brain: <span className="text-signal-cyan">{initData.brain_llm}</span></div>
          <div>🤖 Agent: <span className="text-signal-cyan">{initData.agent_llm}</span></div>
        </div>
      )}

      {/* Status line */}
      <div className="text-xs text-slate-500 h-5 font-mono">
        {!initData ? (
          connectionState === 'connected'
            ? <span className="text-signal-cyan">WAITING FOR TARS INIT{showCursor ? '_' : ' '}</span>
            : <span className="text-yellow-500">CONNECTING{showCursor ? '_' : ' '}</span>
        ) : revealedSteps < totalSteps ? (
          <span className="text-signal-cyan">
            LOADING [{revealedSteps}/{totalSteps}]{showCursor ? '_' : ' '}
          </span>
        ) : (
          <span className="text-signal-green">ALL SYSTEMS NOMINAL ✓</span>
        )}
      </div>
    </div>
  )
}
