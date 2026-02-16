import { useState, useCallback } from 'react'
import { Lock, ArrowRight, AlertTriangle } from 'lucide-react'

interface LoginPageProps {
  onLogin: (token: string) => void
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!passphrase.trim()) return

    setLoading(true)
    setError('')

    try {
      // Try to authenticate with the relay
      const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
      const res = await fetch(`${protocol}//${window.location.host}/api/auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase }),
      })

      if (res.ok) {
        const data = await res.json()
        localStorage.setItem('tars_token', data.token)
        onLogin(data.token)
      } else {
        setError('Invalid passphrase')
      }
    } catch {
      // If no relay, just use the passphrase as a token directly
      localStorage.setItem('tars_token', passphrase)
      onLogin(passphrase)
    } finally {
      setLoading(false)
    }
  }, [passphrase, onLogin])

  return (
    <div className="fixed inset-0 z-[200] bg-void-950 flex items-center justify-center">
      {/* Background glow */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-nebula-blue/10 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 left-1/3 w-[300px] h-[300px] bg-nebula-purple/10 rounded-full blur-[80px]" />
      </div>

      <div className="relative z-10 w-full max-w-sm mx-4">
        {/* Logo */}
        <div className="text-center mb-8">
          <pre className="text-signal-cyan text-[10px] sm:text-xs animate-glow leading-tight inline-block select-none">
{`████████╗ █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
   ██║   ███████║██████╔╝███████╗
   ██║   ██╔══██║██╔══██╗╚════██║
   ██║   ██║  ██║██║  ██║███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝`}
          </pre>
          <p className="text-[10px] tracking-[0.3em] text-slate-500 uppercase mt-4">
            Mission Control // Authentication Required
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="glass-heavy rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Lock size={14} className="text-signal-cyan" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Docking Authorization</span>
          </div>

          <div className="space-y-2">
            <input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder="Enter passphrase..."
              autoFocus
              className="w-full bg-void-800 border border-panel-border rounded-lg px-4 py-3 text-sm text-star-white placeholder-slate-600 outline-none focus:border-signal-cyan/50 focus:shadow-glow-cyan transition-all"
            />

            {error && (
              <div className="flex items-center gap-1.5 text-signal-red text-xs">
                <AlertTriangle size={12} />
                {error}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={!passphrase.trim() || loading}
            className="w-full flex items-center justify-center gap-2 bg-signal-cyan/20 text-signal-cyan border border-signal-cyan/30 rounded-lg py-2.5 text-xs font-bold uppercase tracking-widest hover:bg-signal-cyan/30 hover:shadow-glow-cyan transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="animate-pulse">AUTHENTICATING...</span>
            ) : (
              <>INITIATE DOCKING <ArrowRight size={12} /></>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
