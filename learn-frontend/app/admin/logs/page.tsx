'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

const EVENT_COLORS: Record<string, string> = {
  unit_open: 'bg-blue-100 text-blue-700',
  scroll_milestone: 'bg-purple-100 text-purple-700',
  video_play: 'bg-green-100 text-green-700',
  audio_play: 'bg-teal-100 text-teal-700',
  audio_complete: 'bg-teal-100 text-teal-700',
  quiz_start: 'bg-orange-100 text-orange-700',
  quiz_submit: 'bg-yellow-100 text-yellow-700',
  quiz_abandon: 'bg-red-100 text-red-700',
}

export default function AdminLogs() {
  const router = useRouter()
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try {
        const res = await api.get('/admin/logs?limit=200')
        setLogs(res.data)
      } catch {}
      setLoading(false)
    }
    init()
  }, [router])

  const filtered = filter ? logs.filter(l => l.event_type === filter) : logs
  const eventTypes = [...new Set(logs.map(l => l.event_type))]

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
    </div>
  )

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/admin" className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Admin</Link>
          <h1 className="text-xl font-bold text-[#1E293B]">Interaction Logs</h1>
          <span className="text-sm text-[#94A3B8]">({filtered.length} events)</span>
          <select value={filter} onChange={e => setFilter(e.target.value)}
            className="ml-auto border border-[#E2E8F0] rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#003087]">
            <option value="">All Events</option>
            {eventTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
          <div className="grid grid-cols-5 gap-3 px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase tracking-wide">
            <span>Time</span>
            <span>Event</span>
            <span>Entity</span>
            <span>Value</span>
            <span>Session</span>
          </div>
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-[#94A3B8] text-sm">No events logged yet.</div>
          ) : filtered.map((log: any, i: number) => (
            <div key={i} className="grid grid-cols-5 gap-3 px-5 py-3 border-b border-[#E2E8F0] hover:bg-[#F8F9FC] items-center text-sm">
              <span className="text-xs text-[#94A3B8]">
                {new Date(log.created_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${EVENT_COLORS[log.event_type] || 'bg-gray-100 text-gray-600'}`}>
                {log.event_type}
              </span>
              <span className="font-mono text-xs text-[#003087]">{log.entity_id}</span>
              <span className="text-xs text-[#475569]">{typeof log.value === 'number' ? log.value.toFixed(2) : log.value}</span>
              <span className="font-mono text-xs text-[#94A3B8] truncate">{log.session_id?.slice(0, 12)}...</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}