import { useState, useCallback, useEffect } from 'react'
import { TarsProvider } from './context/ConnectionContext'
import Starfield from './components/Starfield'
import BootSequence from './components/BootSequence'
import MissionControlBar from './components/MissionControlBar'
import ActivityFeed from './components/ActivityFeed'
import TaskPanel from './components/TaskPanel'
import MessagePanel from './components/MessagePanel'
import ProcessControl from './components/ProcessControl'
import Notifications from './components/Notifications'
import ShortcutOverlay from './components/ShortcutOverlay'
import MobileNav from './components/MobileNav'
import AnalyticsPage from './pages/Analytics'
import MemoryPage from './pages/Memory'
import SettingsPage from './pages/Settings'
import EmailPage from './pages/Email'
import { registerShortcut, initShortcuts } from './lib/shortcuts'
import { requestNotificationPermission } from './lib/notifications'

function DashboardLayout() {
  const [activeView, setActiveView] = useState('dashboard')
  const [booted, setBooted] = useState(false)

  // Register shortcuts
  useEffect(() => {
    initShortcuts()
    registerShortcut({ key: '1', description: 'Control view', handler: () => setActiveView('dashboard') })
    registerShortcut({ key: '2', description: 'Email view', handler: () => setActiveView('email') })
    registerShortcut({ key: '3', description: 'Analytics view', handler: () => setActiveView('analytics') })
    registerShortcut({ key: '4', description: 'Memory view', handler: () => setActiveView('memory') })
    registerShortcut({ key: '5', description: 'Settings view', handler: () => setActiveView('settings') })
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
          <div className="h-full flex">
            {/* Left Sidebar: Status + Tasks (desktop only) */}
            <div className="hidden md:flex md:flex-col w-[240px] shrink-0 border-r border-panel-border bg-void-950">
              {/* Process status + controls */}
              <div className="shrink-0 border-b border-panel-border">
                <ProcessControl />
              </div>
              {/* Tasks list */}
              <div className="flex-1 overflow-hidden">
                <TaskPanel />
              </div>
            </div>

            {/* Main Area: Activity Feed + Messages */}
            <div className="flex-1 flex flex-col overflow-hidden bg-void-950">
              {/* Activity Feed — main content */}
              <div className="flex-1 overflow-hidden relative">
                <ActivityFeed />
              </div>
              {/* Messages — compact bottom section (desktop) */}
              <div className="h-48 shrink-0 border-t border-panel-border overflow-hidden hidden md:block">
                <MessagePanel />
              </div>
            </div>
          </div>
        )}

        {activeView === 'analytics' && (
          <div className="h-full bg-void-950">
            <AnalyticsPage />
          </div>
        )}

        {activeView === 'email' && (
          <div className="h-full bg-void-950">
            <EmailPage />
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
