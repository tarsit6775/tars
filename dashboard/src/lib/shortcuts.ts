type ShortcutHandler = () => void

interface Shortcut {
  key: string
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  description: string
  handler: ShortcutHandler
}

const shortcuts: Shortcut[] = []
let initialized = false

function keyMatch(e: KeyboardEvent, s: Shortcut): boolean {
  const keyMatch = e.key.toLowerCase() === s.key.toLowerCase()
  const ctrlMatch = s.ctrl ? (e.ctrlKey || e.metaKey) : true
  const shiftMatch = s.shift ? e.shiftKey : true
  const metaMatch = s.meta ? e.metaKey : true
  return keyMatch && ctrlMatch && shiftMatch && metaMatch
}

export function registerShortcut(shortcut: Shortcut) {
  shortcuts.push(shortcut)
  return () => {
    const i = shortcuts.indexOf(shortcut)
    if (i >= 0) shortcuts.splice(i, 1)
  }
}

export function getShortcuts() {
  return shortcuts.map(s => ({
    key: s.key,
    ctrl: s.ctrl,
    shift: s.shift,
    meta: s.meta,
    description: s.description,
  }))
}

export function initShortcuts() {
  if (initialized) return
  initialized = true
  document.addEventListener('keydown', (e) => {
    // Skip if typing in an input
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      // Only let Escape through
      if (e.key !== 'Escape') return
    }

    for (const s of shortcuts) {
      if (keyMatch(e, s)) {
        e.preventDefault()
        s.handler()
        return
      }
    }
  })
}
