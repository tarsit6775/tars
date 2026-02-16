import { useEffect } from 'react'
import { useTars } from '../context/ConnectionContext'
import { Toaster, toast } from 'sonner'

export default function Notifications() {
  const { connectionState, subsystems, tasks, thinkingBlocks } = useTars()

  // Connection state changes
  useEffect(() => {
    if (connectionState === 'connected') {
      toast.success('Uplink established', { duration: 2000 })
    } else if (connectionState === 'reconnecting') {
      toast.warning('Connection lost -- reconnecting...', { duration: 4000 })
    }
  }, [connectionState])

  // Agent status changes
  useEffect(() => {
    if (subsystems.agent === 'killed') {
      toast.error('KILL SWITCH ACTIVATED', { duration: 10000 })
    }
  }, [subsystems.agent])

  // Task events
  useEffect(() => {
    if (tasks.length === 0) return
    const latest = tasks[0]
    if (latest.status === 'active') {
      toast.info(`Task started: ${latest.text.substring(0, 60)}`, { duration: 3000 })
    }
  }, [tasks])

  // Errors
  useEffect(() => {
    const errors = thinkingBlocks.filter(b => b.type === 'error')
    if (errors.length === 0) return
    const latest = errors[errors.length - 1]
    toast.error(latest.text?.substring(0, 100) || 'Unknown error', { duration: 5000 })
  }, [thinkingBlocks.filter(b => b.type === 'error').length])

  return (
    <Toaster
      position="top-right"
      toastOptions={{
        style: {
          background: 'rgba(12, 19, 34, 0.95)',
          border: '1px solid rgba(26, 45, 71, 0.8)',
          color: '#f1f5f9',
          backdropFilter: 'blur(12px)',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '11px',
        },
      }}
      theme="dark"
    />
  )
}
