'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import Sidebar from '@/components/shared/Sidebar'
import CoachChat from '@/components/shared/CoachChat'

export default function NotificationsPage() {
  const router = useRouter()
  const [notifications, setNotifications] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [coachFor, setCoachFor] = useState<string | null>(null)

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try {
        const res = await api.get('/profile/notifications')
        setNotifications(res.data)
      } catch (err) {
        console.error('Failed to load notifications:', err)
      }
      setLoading(false)
    }
    init()
  }, [router])

  if (loading) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
      </main>
    </div>
  )

  return (
    <div className="flex">
      <Sidebar />
      <CoachChat open={coachFor !== null} onClose={() => setCoachFor(null)} interventionId={coachFor} />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] p-8">
        <div className="max-w-2xl mx-auto">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-[#1E293B]">Notifications</h1>
            <p className="text-[#64748B] mt-1">Every message we've sent you, in case you want to look back</p>
          </div>

          {notifications.length === 0 ? (
            <div className="bg-white rounded-xl border border-[#E2E8F0] p-12 text-center">
              <span className="text-3xl mb-3 block">🔔</span>
              <p className="text-[#94A3B8] text-sm">No notifications yet.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {notifications.map((n: any) => (
                <div key={n.intervention_id} className={`bg-white rounded-xl border p-5 ${n.opened_at ? 'border-[#E2E8F0]' : 'border-blue-300 bg-[#EFF6FF]'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-[#94A3B8]">
                      {new Date(n.requested_at || n.sent_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {!n.opened_at && (
                      <span className="text-xs font-semibold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">New</span>
                    )}
                  </div>
                  <p className="text-sm text-[#1E293B] leading-relaxed">{n.message_sent}</p>
                  <button onClick={() => setCoachFor(n.intervention_id)}
                          className="mt-3 text-xs font-semibold text-[#003087] bg-[#EFF6FF] border border-blue-200 px-3 py-1.5 rounded-full hover:bg-blue-100">
                    💬 Talk about this with your coach
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}