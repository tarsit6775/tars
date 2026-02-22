import { useTars } from '../context/ConnectionContext'
import { BarChart3, PieChart as PieIcon, TrendingUp, Zap, Mail, Send, Inbox, Bell } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid,
} from 'recharts'

const COLORS = ['#06b6d4', '#3b82f6', '#8b5cf6', '#f97316', '#10b981', '#f59e0b', '#ef4444', '#ec4899']

export default function AnalyticsPage() {
  const { stats, actionLog, emailStats, emailEvents } = useTars()

  // Tool usage data
  const toolData = Object.entries(stats.tool_usage || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 12)
    .map(([name, count]) => ({ name, count }))

  // Model usage pie
  const modelData = Object.entries(stats.model_usage || {}).map(([name, count]) => ({
    name: name.includes('haiku') ? 'Haiku' : name.includes('sonnet') ? 'Sonnet' : name,
    value: count,
  }))

  // Success/failure pie
  const successData = [
    { name: 'Success', value: stats.actions_success || 0 },
    { name: 'Failed', value: stats.actions_failed || 0 },
  ].filter(d => d.value > 0)

  // Duration distribution from action log
  const durationBuckets = [
    { range: '<0.5s', count: 0 },
    { range: '0.5-1s', count: 0 },
    { range: '1-2s', count: 0 },
    { range: '2-5s', count: 0 },
    { range: '5-10s', count: 0 },
    { range: '>10s', count: 0 },
  ]
  actionLog.forEach(a => {
    if (a.duration == null) return
    if (a.duration < 0.5) durationBuckets[0].count++
    else if (a.duration < 1) durationBuckets[1].count++
    else if (a.duration < 2) durationBuckets[2].count++
    else if (a.duration < 5) durationBuckets[3].count++
    else if (a.duration < 10) durationBuckets[4].count++
    else durationBuckets[5].count++
  })

  // Token usage over time (approximate from action log chunks)
  const tokenTimeline = (() => {
    const chunks: { time: string; tokens: number }[] = []
    const chunkSize = Math.max(1, Math.floor(actionLog.length / 20))
    for (let i = 0; i < actionLog.length; i += chunkSize) {
      const chunk = actionLog.slice(i, i + chunkSize)
      chunks.push({
        time: chunk[0]?.time || '',
        tokens: chunk.length * 500, // Approximate
      })
    }
    return chunks
  })()

  const StatCard = ({ label, value, color, icon }: { label: string; value: string | number; color: string; icon: React.ReactNode }) => (
    <div className="panel-inset rounded-xl p-4 text-center">
      <div className="flex items-center justify-center gap-1.5 mb-1 text-slate-500">{icon}<span className="text-[9px] uppercase tracking-widest font-bold">{label}</span></div>
      <div className={`text-2xl font-extrabold ${color}`}>{value}</div>
    </div>
  )

  const customTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null
    return (
      <div className="glass-heavy rounded-lg px-3 py-2 text-xs">
        <p className="text-slate-400 mb-1">{label}</p>
        {payload.map((p: any, i: number) => (
          <p key={i} className="text-star-white font-semibold">{p.name}: {p.value}</p>
        ))}
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Top stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Success" value={stats.actions_success || 0} color="text-signal-green" icon={<TrendingUp size={11} />} />
        <StatCard label="Failed" value={stats.actions_failed || 0} color="text-signal-red" icon={<Zap size={11} />} />
        <StatCard label="Tokens" value={`${(((stats.total_tokens_in || 0) + (stats.total_tokens_out || 0)) / 1000).toFixed(1)}K`} color="text-signal-cyan" icon={<BarChart3 size={11} />} />
        <StatCard label="Est. Cost" value={`$${(stats.total_cost || 0).toFixed(3)}`} color="text-signal-amber" icon={<PieIcon size={11} />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Tool usage */}
        <div className="panel-inset rounded-xl p-4">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Tool Usage</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={toolData} layout="vertical" margin={{ left: 80 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} width={75} />
              <Tooltip content={customTooltip} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {toolData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Model split + Success rate */}
        <div className="grid grid-rows-2 gap-4">
          <div className="panel-inset rounded-xl p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Model Split</h3>
            <ResponsiveContainer width="100%" height={90}>
              <PieChart>
                <Pie data={modelData} cx="50%" cy="50%" innerRadius={25} outerRadius={40} dataKey="value" paddingAngle={2}>
                  {modelData.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? '#06b6d4' : '#8b5cf6'} />
                  ))}
                </Pie>
                <Tooltip content={customTooltip} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex justify-center gap-4 text-[9px]">
              {modelData.map((d, i) => (
                <span key={i} className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{ background: i === 0 ? '#06b6d4' : '#8b5cf6' }} />
                  <span className="text-slate-400">{d.name}: {d.value}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="panel-inset rounded-xl p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Success Rate</h3>
            <ResponsiveContainer width="100%" height={90}>
              <PieChart>
                <Pie data={successData} cx="50%" cy="50%" innerRadius={25} outerRadius={40} dataKey="value" paddingAngle={2}>
                  <Cell fill="#10b981" />
                  <Cell fill="#ef4444" />
                </Pie>
                <Tooltip content={customTooltip} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex justify-center gap-4 text-[9px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-signal-green" /><span className="text-slate-400">Success</span></span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-signal-red" /><span className="text-slate-400">Failed</span></span>
            </div>
          </div>
        </div>

        {/* Duration distribution */}
        <div className="panel-inset rounded-xl p-4">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Response Time Distribution</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={durationBuckets}>
              <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#64748b' }} />
              <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
              <Tooltip content={customTooltip} />
              <Bar dataKey="count" fill="#3b82f6" fillOpacity={0.7} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Token timeline */}
        <div className="panel-inset rounded-xl p-4">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Activity Over Time</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={tokenTimeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2d47" />
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#64748b' }} />
              <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
              <Tooltip content={customTooltip} />
              <Line type="monotone" dataKey="tokens" stroke="#06b6d4" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ─── Email Analytics Section ─── */}
      <div className="border-t border-slate-800/50 pt-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3 flex items-center gap-2">
          <Mail size={14} className="text-signal-cyan" /> Email Analytics
        </h2>

        {/* Email stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <StatCard label="Unread" value={emailStats.unread} color="text-signal-cyan" icon={<Inbox size={11} />} />
          <StatCard label="Sent Today" value={emailStats.sent_today} color="text-signal-green" icon={<Send size={11} />} />
          <StatCard label="Rules" value={emailStats.rules_count} color="text-signal-purple" icon={<Bell size={11} />} />
          <StatCard label="Scheduled" value={emailStats.scheduled_pending} color="text-signal-amber" icon={<Mail size={11} />} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Top senders chart */}
          <div className="panel-inset rounded-xl p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Top Senders</h3>
            {emailStats.top_senders && emailStats.top_senders.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={emailStats.top_senders.map((s: { name: string; count: number }) => ({
                  name: s.name.length > 20 ? s.name.substring(0, 20) + '…' : s.name,
                  count: s.count,
                }))} layout="vertical" margin={{ left: 100 }}>
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: '#94a3b8' }} width={95} />
                  <Tooltip content={customTooltip} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {emailStats.top_senders.map((_: unknown, i: number) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[180px] flex items-center justify-center text-slate-600 text-xs">No sender data yet</div>
            )}
          </div>

          {/* Email event breakdown */}
          <div className="panel-inset rounded-xl p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Email Activity</h3>
            {(() => {
              const eventCounts: Record<string, number> = {}
              emailEvents.forEach(e => {
                const type = e.type || 'other'
                eventCounts[type] = (eventCounts[type] || 0) + 1
              })
              const eventData = Object.entries(eventCounts)
                .map(([name, value]) => ({
                  name: name.replace('email_', '').replace(/_/g, ' '),
                  value,
                }))
                .sort((a, b) => b.value - a.value)

              if (eventData.length === 0) {
                return <div className="h-[180px] flex items-center justify-center text-slate-600 text-xs">No email events yet</div>
              }

              return (
                <>
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={eventData} cx="50%" cy="50%" innerRadius={30} outerRadius={50} dataKey="value" paddingAngle={2}>
                        {eventData.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={customTooltip} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-wrap justify-center gap-3 text-[9px] mt-2">
                    {eventData.slice(0, 6).map((d, i) => (
                      <span key={i} className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                        <span className="text-slate-400">{d.name}: {d.value}</span>
                      </span>
                    ))}
                  </div>
                </>
              )
            })()}
          </div>

          {/* Rules activity */}
          <div className="panel-inset rounded-xl p-4 lg:col-span-2">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-3">Email Overview</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <div className="text-lg font-bold text-signal-cyan">{emailStats.inbox_total}</div>
                <div className="text-[9px] text-slate-500 uppercase tracking-wider">Total Inbox</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-signal-green">{emailStats.rules_triggered_today}</div>
                <div className="text-[9px] text-slate-500 uppercase tracking-wider">Rules Triggered Today</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-signal-amber">{emailStats.drafts}</div>
                <div className="text-[9px] text-slate-500 uppercase tracking-wider">Drafts</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold" style={{ color: emailStats.monitor_active ? '#10b981' : '#ef4444' }}>
                  {emailStats.monitor_active ? 'ACTIVE' : 'OFF'}
                </div>
                <div className="text-[9px] text-slate-500 uppercase tracking-wider">Inbox Monitor</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
