import { useEffect, useState } from 'react'
import { getShortcuts, registerShortcut, initShortcuts } from '../lib/shortcuts'
import { Keyboard, X } from 'lucide-react'

export default function ShortcutOverlay() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    initShortcuts()
    registerShortcut({
      key: '?',
      description: 'Show keyboard shortcuts',
      handler: () => setVisible(v => !v),
    })
  }, [])

  if (!visible) return null

  const shortcuts = getShortcuts()

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-void-950/80 backdrop-blur-sm" onClick={() => setVisible(false)}>
      <div className="glass-heavy rounded-2xl p-6 w-96 max-w-[90vw]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Keyboard size={14} className="text-signal-cyan" />
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Keyboard Shortcuts</h2>
          </div>
          <button onClick={() => setVisible(false)} className="text-slate-500 hover:text-star-white">
            <X size={14} />
          </button>
        </div>

        <div className="space-y-2">
          {shortcuts.map((s, i) => (
            <div key={i} className="flex items-center justify-between py-1.5 border-b border-panel-border/50">
              <span className="text-xs text-slate-400">{s.description}</span>
              <kbd className="px-2 py-0.5 bg-void-800 border border-panel-border rounded text-[10px] font-bold text-signal-cyan">
                {[s.ctrl && 'Ctrl', s.shift && 'Shift', s.meta && 'Cmd', s.key.toUpperCase()].filter(Boolean).join(' + ')}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
