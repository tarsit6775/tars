import { useState } from 'react'
import { useTars } from '../context/ConnectionContext'
import { Settings as SettingsIcon, Shield, MessageSquare, Wifi, Sliders, Link2 } from 'lucide-react'
import clsx from 'clsx'

export default function SettingsPage() {
  const { updateConfig, connectionState, subsystems, setWsUrl, setAuthToken } = useTars()
  const [humor, setHumor] = useState(75)
  const [rateLimit, setRateLimit] = useState(30)
  const [confirmDestructive, setConfirmDestructive] = useState(true)
  const [relayUrl, setRelayUrl] = useState('')
  const [authToken, setAuthTokenLocal] = useState('')

  const Section = ({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) => (
    <div className="panel-inset rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 pb-2 border-b border-panel-border">
        <span className="text-signal-cyan">{icon}</span>
        <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{title}</h3>
      </div>
      {children}
    </div>
  )

  const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div className="flex items-center justify-between py-2">
      <span className="text-xs text-slate-400">{label}</span>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  )

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 max-w-2xl mx-auto">
      <Section title="Agent" icon={<Sliders size={13} />}>
        <Row label="Humor Level">
          <input
            type="range"
            min={0} max={100}
            value={humor}
            onChange={(e) => {
              setHumor(Number(e.target.value))
              updateConfig('agent.humor_level', Number(e.target.value))
            }}
            className="w-24 accent-signal-cyan"
          />
          <span className="text-xs text-signal-cyan font-bold w-8 text-right">{humor}%</span>
        </Row>
        <Row label="Force Model">
          <select
            onChange={(e) => updateConfig('anthropic.force_model', e.target.value)}
            className="bg-void-800 border border-panel-border text-xs text-star-white rounded px-2 py-1 outline-none"
          >
            <option value="auto">Auto (Hybrid)</option>
            <option value="haiku">Haiku (Fast)</option>
            <option value="sonnet">Sonnet (Smart)</option>
          </select>
        </Row>
      </Section>

      <Section title="Safety" icon={<Shield size={13} />}>
        <Row label="Confirm Destructive Actions">
          <button
            onClick={() => {
              const v = !confirmDestructive
              setConfirmDestructive(v)
              updateConfig('safety.confirm_destructive', v)
            }}
            className={clsx(
              'w-10 h-5 rounded-full transition-all relative',
              confirmDestructive ? 'bg-signal-green' : 'bg-slate-700'
            )}
          >
            <div className={clsx(
              'w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all',
              confirmDestructive ? 'left-5' : 'left-0.5'
            )} />
          </button>
        </Row>
        <Row label="Kill Words">
          <span className="text-[10px] text-slate-500 font-mono">STOP, HALT, KILL</span>
        </Row>
      </Section>

      <Section title="iMessage" icon={<MessageSquare size={13} />}>
        <Row label="Rate Limit">
          <input
            type="range"
            min={5} max={120}
            value={rateLimit}
            onChange={(e) => {
              setRateLimit(Number(e.target.value))
              updateConfig('imessage.rate_limit', Number(e.target.value))
            }}
            className="w-24 accent-signal-cyan"
          />
          <span className="text-xs text-signal-cyan font-bold w-8 text-right">{rateLimit}s</span>
        </Row>
      </Section>

      <Section title="Connection" icon={<Wifi size={13} />}>
        <Row label="WebSocket Status">
          <span className={clsx(
            'text-xs font-bold uppercase',
            connectionState === 'connected' ? 'text-signal-green' : 'text-signal-red'
          )}>
            {connectionState}
          </span>
        </Row>
        <Row label="Agent Status">
          <span className={clsx(
            'text-xs font-bold uppercase',
            subsystems.agent === 'online' ? 'text-signal-green'
              : subsystems.agent === 'working' ? 'text-signal-amber'
              : 'text-signal-red'
          )}>
            {subsystems.agent}
          </span>
        </Row>
        <div className="space-y-2 pt-2 border-t border-panel-border mt-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Cloud Relay URL</label>
          <div className="flex items-center gap-2">
            <div className="flex-1 flex items-center gap-1.5 bg-void-800 border border-panel-border rounded px-2 py-1.5">
              <Link2 size={11} className="text-slate-600" />
              <input
                type="text"
                value={relayUrl}
                onChange={(e) => setRelayUrl(e.target.value)}
                placeholder="wss://your-relay.railway.app/ws"
                className="flex-1 bg-transparent text-xs text-star-white placeholder-slate-600 outline-none"
              />
            </div>
            <button
              onClick={() => relayUrl && setWsUrl(relayUrl)}
              className="px-3 py-1.5 bg-signal-blue/20 text-signal-blue text-[10px] font-bold rounded hover:bg-signal-blue/30 transition-colors"
            >
              Connect
            </button>
          </div>
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mt-2 block">Auth Token</label>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={authToken}
              onChange={(e) => setAuthTokenLocal(e.target.value)}
              placeholder="Your relay auth token"
              className="flex-1 bg-void-800 border border-panel-border rounded px-2 py-1.5 text-xs text-star-white placeholder-slate-600 outline-none"
            />
            <button
              onClick={() => authToken && setAuthToken(authToken)}
              className="px-3 py-1.5 bg-signal-purple/20 text-signal-purple text-[10px] font-bold rounded hover:bg-signal-purple/30 transition-colors"
            >
              Set
            </button>
          </div>
        </div>
      </Section>
    </div>
  )
}
