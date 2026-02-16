import { Brain, ListTodo, MessageSquare, BarChart3, Settings } from 'lucide-react'
import clsx from 'clsx'

interface MobileNavProps {
  activeView: string
  onViewChange: (view: string) => void
}

const TABS = [
  { id: 'dashboard', icon: Brain, label: 'Control' },
  { id: 'tasks', icon: ListTodo, label: 'Tasks' },
  { id: 'messages', icon: MessageSquare, label: 'Messages' },
  { id: 'analytics', icon: BarChart3, label: 'Stats' },
  { id: 'settings', icon: Settings, label: 'Settings' },
]

export default function MobileNav({ activeView, onViewChange }: MobileNavProps) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 glass-heavy border-t border-panel-border safe-area-bottom">
      <div className="flex items-center justify-around h-14">
        {TABS.map(tab => {
          const Icon = tab.icon
          const active = activeView === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => onViewChange(tab.id)}
              className={clsx(
                'flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg transition-all min-w-[56px]',
                active ? 'text-signal-cyan' : 'text-slate-600'
              )}
            >
              <Icon size={18} />
              <span className="text-[8px] font-bold uppercase tracking-wider">{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
