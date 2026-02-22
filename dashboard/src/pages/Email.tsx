import { useTars } from '../context/ConnectionContext'
import {
  Mail, Inbox, Send, Clock, Shield, AlertTriangle,
  MailOpen, Flag, Calendar, BarChart3, ArrowRight,
  CheckCircle2, XCircle, Zap, Bell, AlarmClock,
  Palmtree, Heart, ClipboardList, Sparkles, Paperclip, Star,
  ListChecks, GitBranch, PenLine, Search, UserCheck, MessageSquare,
  Smile, FolderOpen, FileText, Tag, Newspaper, BotMessageSquare,
  Signature, Users, Archive,
} from 'lucide-react'
import clsx from 'clsx'

function StatCard({ icon, label, value, color }: {
  icon: React.ReactNode
  label: string
  value: string | number
  color: string
}) {
  return (
    <div className="glass rounded-lg p-3 flex items-center gap-3 min-w-0">
      <div className={clsx('w-8 h-8 rounded-md flex items-center justify-center shrink-0', color)}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-lg font-bold text-star-white tabular-nums">{value}</div>
      </div>
    </div>
  )
}

function EventTypeIcon({ type }: { type: string }) {
  switch (type) {
    case 'sent':
      return <Send size={12} className="text-signal-cyan" />
    case 'received':
      return <Inbox size={12} className="text-signal-green" />
    case 'rule_triggered':
      return <Zap size={12} className="text-signal-amber" />
    case 'batch_action':
      return <BarChart3 size={12} className="text-signal-purple" />
    case 'scheduled_sent':
      return <Calendar size={12} className="text-signal-blue" />
    case 'action':
      return <ArrowRight size={12} className="text-slate-400" />
    case 'snoozed':
      return <AlarmClock size={12} className="text-signal-amber" />
    case 'resurfaced':
      return <Bell size={12} className="text-signal-green" />
    case 'digest':
      return <BarChart3 size={12} className="text-signal-cyan" />
    case 'ooo_set':
    case 'ooo_replied':
    case 'ooo_expired':
      return <Palmtree size={12} className="text-signal-green" />
    case 'followup_overdue':
      return <ClipboardList size={12} className="text-signal-amber" />
    case 'auto_digest':
      return <BarChart3 size={12} className="text-signal-purple" />
    case 'clean_sweep':
      return <Sparkles size={12} className="text-signal-cyan" />
    case 'auto_triage':
      return <Shield size={12} className="text-signal-blue" />
    case 'unsubscribed':
      return <XCircle size={12} className="text-signal-amber" />
    case 'vip_detected':
      return <Star size={12} className="text-signal-amber" />
    case 'inbox_zero_progress':
      return <CheckCircle2 size={12} className="text-signal-green" />
    case 'attachment_indexed':
      return <Paperclip size={12} className="text-signal-blue" />
    case 'relationship_scored':
      return <Heart size={12} className="text-signal-purple" />
    case 'security_scan':
      return <Shield size={12} className="text-signal-blue" />
    case 'phishing_detected':
      return <AlertTriangle size={12} className="text-signal-red" />
    case 'sender_blocked':
      return <XCircle size={12} className="text-signal-red" />
    case 'sender_trusted':
      return <CheckCircle2 size={12} className="text-signal-green" />
    case 'action_extracted':
      return <ClipboardList size={12} className="text-signal-amber" />
    case 'meeting_extracted':
      return <Calendar size={12} className="text-signal-blue" />
    case 'reminder_created':
      return <AlarmClock size={12} className="text-signal-amber" />
    case 'action_completed':
      return <ListChecks size={12} className="text-signal-green" />
    case 'workflow_created':
      return <GitBranch size={12} className="text-nebula-purple" />
    case 'workflow_triggered':
      return <Zap size={12} className="text-signal-amber" />
    case 'workflow_completed':
      return <GitBranch size={12} className="text-signal-green" />
    case 'email_composed':
      return <PenLine size={12} className="text-nebula-purple" />
    case 'email_rewritten':
      return <PenLine size={12} className="text-signal-blue" />
    case 'email_proofread':
      return <Search size={12} className="text-signal-amber" />
    case 'email_delegated':
      return <UserCheck size={12} className="text-signal-blue" />
    case 'delegation_completed':
      return <UserCheck size={12} className="text-signal-green" />
    case 'delegation_nudged':
      return <AlarmClock size={12} className="text-signal-amber" />
    case 'search_index_built':
      return <Search size={12} className="text-signal-green" />
    case 'email_search':
      return <Search size={12} className="text-signal-blue" />
    case 'conversation_recalled':
      return <MessageSquare size={12} className="text-nebula-purple" />
    default:
      return <Mail size={12} className="text-slate-500" />
  }
}

export default function EmailPage() {
  const { emailEvents, emailStats } = useTars()

  // Reversed for newest-first
  const recentEvents = [...emailEvents].reverse().slice(0, 50)

  // Compute event type breakdown
  const eventCounts: Record<string, number> = {}
  emailEvents.forEach(e => {
    eventCounts[e.type] = (eventCounts[e.type] || 0) + 1
  })

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Mail size={20} className="text-signal-cyan" />
        <h2 className="text-sm font-bold uppercase tracking-widest text-star-white">Email Command Center</h2>
        <div className="flex items-center gap-1.5 ml-auto">
          <div className={clsx(
            'w-2 h-2 rounded-full',
            emailStats.monitor_active ? 'bg-signal-green animate-pulse' : 'bg-signal-red'
          )} />
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            Monitor {emailStats.monitor_active ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
        <StatCard
          icon={<MailOpen size={16} className="text-white" />}
          label="Unread"
          value={emailStats.unread}
          color="bg-signal-cyan/20"
        />
        <StatCard
          icon={<Inbox size={16} className="text-white" />}
          label="Inbox"
          value={emailStats.inbox_total}
          color="bg-signal-blue/20"
        />
        <StatCard
          icon={<Send size={16} className="text-white" />}
          label="Sent Today"
          value={emailStats.sent_today}
          color="bg-signal-green/20"
        />
        <StatCard
          icon={<Flag size={16} className="text-white" />}
          label="Drafts"
          value={emailStats.drafts}
          color="bg-signal-amber/20"
        />
        <StatCard
          icon={<Shield size={16} className="text-white" />}
          label="Rules"
          value={emailStats.rules_count}
          color="bg-signal-purple/20"
        />
        <StatCard
          icon={<Zap size={16} className="text-white" />}
          label="Rules Hit"
          value={emailStats.rules_triggered_today}
          color="bg-thrust/20"
        />
        <StatCard
          icon={<Calendar size={16} className="text-white" />}
          label="Scheduled"
          value={emailStats.scheduled_pending}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<AlarmClock size={16} className="text-white" />}
          label="Snoozed"
          value={emailStats.snoozed_count || 0}
          color="bg-signal-amber/20"
        />
        <StatCard
          icon={<Palmtree size={16} className="text-white" />}
          label="OOO"
          value={emailStats.ooo_active ? 'ACTIVE' : 'Off'}
          color={emailStats.ooo_active ? 'bg-signal-green/20' : 'bg-void-gray/30'}
        />
        <StatCard
          icon={<Heart size={16} className="text-white" />}
          label="Health"
          value={emailStats.health_score != null ? `${emailStats.health_score}/100` : '—'}
          color="bg-signal-green/20"
        />
        <StatCard
          icon={<Sparkles size={16} className="text-white" />}
          label="Zero Streak"
          value={emailStats.inbox_zero_streak != null ? `${emailStats.inbox_zero_streak}d` : '—'}
          color="bg-thrust/20"
        />
        <StatCard
          icon={<Paperclip size={16} className="text-white" />}
          label="Attachments"
          value={emailStats.attachment_count ?? '—'}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<Star size={16} className="text-white" />}
          label="VIPs"
          value={emailStats.vip_count ?? 0}
          color="bg-signal-amber/20"
        />
        <StatCard
          icon={<Shield size={16} className="text-white" />}
          label="Threats"
          value={emailStats.security_threats ?? 0}
          color="bg-signal-red/20"
        />
        <StatCard
          icon={<ListChecks size={16} className="text-white" />}
          label="Actions"
          value={emailStats.pending_actions ?? 0}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<GitBranch size={16} className="text-white" />}
          label="Workflows"
          value={emailStats.active_workflows ?? 0}
          color="bg-nebula-purple/20"
        />
        <StatCard
          icon={<PenLine size={16} className="text-white" />}
          label="Composed"
          value={emailStats.compositions_today ?? 0}
          color="bg-nebula-purple/20"
        />
        <StatCard
          icon={<UserCheck size={16} className="text-white" />}
          label="Delegations"
          value={emailStats.active_delegations ?? 0}
          color="bg-signal-blue/20"
        />
        <StatCard
          icon={<Search size={16} className="text-white" />}
          label="Search Index"
          value={emailStats.search_index_size ?? 0}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<Smile size={16} className="text-white" />}
          label="Sentiment"
          value={emailStats.sentiment_avg ?? 0}
          color="bg-signal-green/20"
        />
        <StatCard
          icon={<FolderOpen size={16} className="text-white" />}
          label="Smart Folders"
          value={emailStats.smart_folder_count ?? 0}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<FileText size={16} className="text-white" />}
          label="Summarized"
          value={emailStats.threads_summarized ?? 0}
          color="bg-nebula-purple/20"
        />
        <StatCard
          icon={<Tag size={16} className="text-white" />}
          label="Labels"
          value={emailStats.labels_count ?? 0}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<Newspaper size={16} className="text-white" />}
          label="Newsletters"
          value={emailStats.newsletters_tracked ?? 0}
          color="bg-signal-amber/20"
        />
        <StatCard
          icon={<BotMessageSquare size={16} className="text-white" />}
          label="Auto-Responses"
          value={emailStats.auto_responses_active ?? 0}
          color="bg-thrust-orange/20"
        />
        <StatCard
          icon={<Signature size={16} className="text-white" />}
          label="Signatures"
          value={emailStats.signatures_count ?? 0}
          color="bg-nebula-blue/20"
        />
        <StatCard
          icon={<Users size={16} className="text-white" />}
          label="Aliases"
          value={emailStats.aliases_count ?? 0}
          color="bg-nebula-purple/20"
        />
        <StatCard
          icon={<Archive size={16} className="text-white" />}
          label="Exports"
          value={emailStats.exports_count ?? 0}
          color="bg-signal-amber/20"
        />
        <StatCard
          icon={<Bell size={16} className="text-white" />}
          label="Events"
          value={emailEvents.length}
          color="bg-nebula-purple/20"
        />
      </div>

      {/* Two-column: Activity Feed + Top Senders */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* Activity Feed */}
        <div className="glass rounded-lg overflow-hidden flex flex-col" style={{ maxHeight: 'calc(100vh - 280px)' }}>
          <div className="flex items-center gap-2 px-3 py-2 border-b border-panel-border bg-panel-surface/50 shrink-0">
            <BarChart3 size={13} className="text-signal-amber" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Email Activity Feed</span>
            <span className="text-[10px] text-slate-600 ml-auto">{emailEvents.length} events</span>
          </div>

          {/* Event type breakdown bar */}
          {emailEvents.length > 0 && (
            <div className="flex items-center gap-3 px-3 py-1.5 border-b border-panel-border/50 bg-panel-surface/30 shrink-0">
              {Object.entries(eventCounts).map(([type, count]) => (
                <div key={type} className="flex items-center gap-1">
                  <EventTypeIcon type={type} />
                  <span className="text-[9px] text-slate-500 uppercase">{type.replace('_', ' ')}</span>
                  <span className="text-[9px] font-bold text-slate-400">{count}</span>
                </div>
              ))}
            </div>
          )}

          {/* Event list */}
          <div className="flex-1 overflow-y-auto">
            {recentEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-700 py-12">
                <Mail size={32} className="mb-2 text-slate-800" />
                <span className="text-[11px]">No email activity yet</span>
                <span className="text-[9px] text-slate-800 mt-1">Events will appear as TARS processes emails</span>
              </div>
            ) : (
              recentEvents.map(evt => (
                <div
                  key={evt.id}
                  className="flex items-start gap-2 px-3 py-2 border-b border-panel-border/30 hover:bg-white/[0.01] transition-colors animate-fade-in"
                >
                  <div className="mt-0.5 shrink-0">
                    <EventTypeIcon type={evt.type} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-slate-300 truncate" title={evt.detail}>
                      {evt.detail}
                    </div>
                  </div>
                  <div className="text-[9px] text-slate-600 shrink-0">{evt.time}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right sidebar: Top Senders + Quick Stats */}
        <div className="space-y-4">
          {/* Top Senders */}
          <div className="glass rounded-lg overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-panel-border bg-panel-surface/50">
              <AlertTriangle size={13} className="text-signal-amber" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Top Senders</span>
            </div>
            <div className="p-2">
              {emailStats.top_senders.length === 0 ? (
                <div className="text-[10px] text-slate-700 text-center py-4">No data yet</div>
              ) : (
                emailStats.top_senders.slice(0, 8).map((sender, i) => (
                  <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-white/[0.02]">
                    <div className="w-5 h-5 rounded-full bg-signal-cyan/10 flex items-center justify-center text-[9px] font-bold text-signal-cyan shrink-0">
                      {sender.name.charAt(0).toUpperCase()}
                    </div>
                    <span className="text-[10px] text-slate-400 flex-1 truncate" title={sender.name}>
                      {sender.name}
                    </span>
                    <span className="text-[10px] font-bold text-star-white tabular-nums">{sender.count}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Event Breakdown */}
          <div className="glass rounded-lg overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-panel-border bg-panel-surface/50">
              <BarChart3 size={13} className="text-signal-cyan" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Event Breakdown</span>
            </div>
            <div className="p-2 space-y-1">
              {[
                { label: 'Sent', type: 'sent', icon: <Send size={11} />, color: 'text-signal-cyan' },
                { label: 'Received', type: 'received', icon: <Inbox size={11} />, color: 'text-signal-green' },
                { label: 'Rules Hit', type: 'rule_triggered', icon: <Zap size={11} />, color: 'text-signal-amber' },
                { label: 'Batch Ops', type: 'batch_action', icon: <BarChart3 size={11} />, color: 'text-signal-purple' },
                { label: 'Scheduled', type: 'scheduled_sent', icon: <Calendar size={11} />, color: 'text-signal-blue' },
                { label: 'Other', type: 'action', icon: <ArrowRight size={11} />, color: 'text-slate-400' },
              ].map(row => (
                <div key={row.type} className="flex items-center gap-2 px-2 py-1">
                  <span className={clsx('shrink-0', row.color)}>{row.icon}</span>
                  <span className="text-[10px] text-slate-500 flex-1">{row.label}</span>
                  <span className="text-[10px] font-bold text-star-white tabular-nums">
                    {eventCounts[row.type] || 0}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Monitor Status */}
          <div className="glass rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <div className={clsx(
                'w-2 h-2 rounded-full',
                emailStats.monitor_active ? 'bg-signal-green animate-pulse' : 'bg-signal-red'
              )} />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Inbox Monitor
              </span>
            </div>
            <div className="text-[10px] text-slate-500">
              {emailStats.monitor_active
                ? 'Polling for new emails, applying rules, processing scheduled sends.'
                : 'Monitor is inactive. Enable inbox_monitor in config.yaml to activate.'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
