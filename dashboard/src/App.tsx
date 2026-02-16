import { useState, useCallback, useEffect } from 'react'
import { TarsProvider } from './context/ConnectionContext'
import Starfield from './components/Starfield'
import BootSequence from './components/BootSequence'
import MissionControlBar from './components/MissionControlBar'
import ThinkingStream from './components/ThinkingStream'
import TaskPanel from './components/TaskPanel'
import MessagePanel from './components/MessagePanel'
import ActionLog from './components/ActionLog'
import ProcessControl from './components/ProcessControl'
import ConsoleOutput from './components/ConsoleOutput'
import Notifications from './components/Notifications'
import ShortcutOverlay from './components/ShortcutOverlay'
import MobileNav from './components/MobileNav'
import AnalyticsPage from './pages/Analytics'
import MemoryPage from './pages/Memory'
import SettingsPage from './pages/Settings'
import { registerShortcut, initShortcuts } from './lib/shortcuts'
import { requestNotificationPermission } from './lib/notifications'

function DashboardLayout() {
  const [activeView, setActiveView] = useState('dashboard')
  const [booted, setBooted] = useState(false)

  // Register shortcuts
  useEffect(() => {
    initShortcuts()
    registerShortcut({ key: '1', description: 'Control view', handler: () => setActiveView('dashboard') })
    registerShortcut({ key: '2', description: 'Analytics view', handler: () => setActiveView('analytics') })
    registerShortcut({ key: '3', description: 'Memory view', handler: () => setActiveView('memory') })
    registerShortcut({ key: '4', description: 'Settings view', handler: () => setActiveView('settings') })
    registerShortcut({ key: 'k', ctrl: true, description: 'Focus task input', handler: () => {
      const el = document.querySelector<HTMLInputElement>('.task-input-focus')
      el?.focus()
    }})
    registerShortcut({ key: 'Escape', description: 'Close overlays', handler: () => {} })
    requestNotificationPermission()
  }, [])

  const handleBoot = useCallback(() => setBooted(true), [])

  return (
    <div className="h-screen flex flex-col overflow-hidden relative">
      {/* Starfield background */}
      <Starfield />

      {/* Boot sequence */}
      {!booted && <BootSequence onComplete={handleBoot} />}

      {/* Scanline overlay */}
      <div className="fixed inset-0 z-[1] scanline pointer-events-none" />

      {/* Mission Control Bar */}
      <MissionControlBar activeView={activeView} onViewChange={setActiveView} />

      {/* Main content */}
      <main className="relative z-10 flex-1 overflow-hidden">
        {activeView === 'dashboard' && (
          <div className="h-full flex flex-col">
            {/* Desktop: 3-column layout */}
            <div className="flex-1 hidden md:grid md:grid-cols-[220px_1fr_260px] gap-px bg-panel-border overflow-hidden">
              {/* Left: Process Control + Tasks */}
              <div className="bg-void-950 overflow-hidden flex flex-col">
                <div className="shrink-0 border-b border-panel-border" style={{ maxHeight: '45%' }}>
                  <ProcessControl />
                </div>
                <div className="flex-1 overflow-hidden">
                  <TaskPanel />
                </div>
              </div>

              {/* Center: Live Activity (main) + Thinking Stream */}
              <div className="bg-void-950 overflow-hidden flex flex-col">
                <div className="flex-[3] overflow-hidden relative border-b border-panel-border">
                  <ConsoleOutput />
                </div>
                <div className="flex-[2] overflow-hidden relative">
                  <ThinkingStream />
                </div>
              </div>

              {/* Right: iMessage (conversation only) */}
              <div className="bg-void-950 overflow-hidden">
                <MessagePanel />
              </div>
            </div>

            {/* Mobile */}
            <div className="flex-1 md:hidden overflow-hidden bg-void-950 flex flex-col">
              <div className="shrink-0 border-b border-panel-border" style={{ maxHeight: '35%' }}>
                <ProcessControl />
              </div>
              <div className="flex-1 overflow-hidden relative">
                <ConsoleOutput />
              </div>
            </div>

            {/* Bottom: Action Log */}
            <div className="h-40 border-t border-panel-border bg-void-950 hidden md:block overflow-hidden">
              <ActionLog />
            </div>
          </div>
        )}

        {activeView === 'analytics' && (
          <div className="h-full bg-void-950">
            <AnalyticsPage />
          </div>
        )}

        {activeView === 'memory' && (
          <div className="h-full bg-void-950">
            <MemoryPage />
          </div>
        )}

        {activeView === 'settings' && (
          <div className="h-full bg-void-950">
            <SettingsPage />
          </div>
        )}

        {/* Mobile-only task and message views */}
        {activeView === 'tasks' && (
          <div className="h-full bg-void-950 md:hidden">
            <TaskPanel />
          </div>
        )}

        {activeView === 'messages' && (
          <div className="h-full bg-void-950 md:hidden">
            <MessagePanel />
          </div>
        )}
      </main>

      {/* Mobile nav */}
      <MobileNav activeView={activeView} onViewChange={setActiveView} />

      {/* Notifications */}
      <Notifications />

      {/* Shortcut overlay */}
      <ShortcutOverlay />
    </div>
  )
}

export default function App() {
  return (
    <TarsProvider>
      <DashboardLayout />
    </TarsProvider>
  )
}
