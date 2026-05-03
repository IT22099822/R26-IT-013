'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import Sidebar from '@/components/shared/Sidebar'

const VARK_INFO: Record<string, { label: string; desc: string; icon: string }> = {
  V: { label: 'Visual', desc: 'You learn best through images, diagrams, and watching things in action.', icon: '👁️' },
  A: { label: 'Auditory', desc: 'You learn best through listening and talking things through.', icon: '👂' },
  R: { label: 'Reading & Writing', desc: 'You learn best through reading and writing text.', icon: '📝' },
  K: { label: 'Hands-on', desc: 'You learn best through practice and doing, not just reading about it.', icon: '✋' },
}

export default function ProgressPage() {
  const router = useRouter()
  const [profile, setProfile] = useState<any>(null)
  const [stats, setStats] = useState<any[]>([])
  const [progressData, setProgressData] = useState<any>(null)
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try {
        const [profileRes, statsRes, progressRes, nodesRes] = await Promise.all([
          api.get('/profile/me'),
          api.get('/profile/stats'),
          api.get('/profile/progress'),
          api.get('/content/nodes'),
        ])
        setProfile(profileRes.data)
        setStats(statsRes.data)
        setProgressData(progressRes.data)
        setNodes(nodesRes.data)
      } catch (err) {
        console.error('Failed to load progress page data:', err)
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

  const latestStats = stats[stats.length - 1]
  const varkInfo = VARK_INFO[profile?.vark_label] || null

  // Growth trend, described in plain language — never shows the raw
  // theta number. Compares the earliest and most recent estimates.
  const thetaHistory: { date: string; theta: number }[] = progressData?.irt_theta_history || []
  let growthMessage = "Keep going — your progress will start showing here soon."
  if (thetaHistory.length >= 2) {
    const first = thetaHistory[0].theta
    const last = thetaHistory[thetaHistory.length - 1].theta
    if (last > first + 0.15) {
      growthMessage = "You're growing steadily! Keep up the great work."
    } else if (last < first - 0.15) {
      growthMessage = "It's been a bit tricky lately — that's completely normal. Revisiting a few earlier lessons could help."
    } else {
      growthMessage = "You're holding steady. A little more practice could help you grow further."
    }
  }

  // Simple hand-rolled sparkline — no charting library needed
  const sparkPoints = thetaHistory.length >= 2 ? (() => {
    const values = thetaHistory.map(h => h.theta)
    const min = Math.min(...values), max = Math.max(...values)
    const range = max - min || 1
    return values.map((v, i) => {
      const x = (i / (values.length - 1)) * 280
      const y = 50 - ((v - min) / range) * 40
      return `${x},${y}`
    }).join(' ')
  })() : null

  const gapNodeIds: string[] = progressData?.current_gaps || []
  const gapNodes = gapNodeIds.map(id => nodes.find(n => n.node_id === id)).filter(Boolean)

  return (
    <div className="flex">
      <Sidebar userName={profile?.email?.split('@')[0] || ''} />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] p-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#1E293B]">My Progress</h1>
          <p className="text-[#64748B] mt-1">Here's how your learning journey is going</p>
        </div>

        {/* Growth + Learning Style */}
        <div className="grid grid-cols-2 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
            <p className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wide mb-2">Your Growth</p>
            <p className="text-[#1E293B] font-medium mb-3">{growthMessage}</p>
            {sparkPoints ? (
              <svg viewBox="0 0 280 50" className="w-full h-12">
                <polyline points={sparkPoints} fill="none" stroke="#003087" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            ) : (
              <div className="h-12 flex items-center">
                <span className="text-xs text-[#94A3B8]">Complete a few more lessons to see your trend</span>
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
            <p className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wide mb-2">How You Learn Best</p>
            {varkInfo ? (
              <div className="flex items-start gap-3">
                <span className="text-3xl">{varkInfo.icon}</span>
                <div>
                  <p className="font-bold text-[#1E293B]">{varkInfo.label}</p>
                  <p className="text-sm text-[#64748B] mt-0.5">{varkInfo.desc}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-[#94A3B8]">Keep learning — we're still figuring out your style.</p>
            )}
          </div>
        </div>

        {/* Areas to revisit */}
        {gapNodes.length > 0 && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 mb-8">
            <h2 className="font-bold text-[#1E293B] mb-1">Worth Revisiting</h2>
            <p className="text-sm text-[#64748B] mb-4">These topics could use a bit more practice before moving on.</p>
            <div className="grid grid-cols-2 gap-3">
              {gapNodes.map((n: any) => (
                <Link key={n.node_id} href={`/learn/${n.node_id}`}
                  className="flex items-center justify-between p-3 bg-[#FFF7ED] border border-orange-200 rounded-xl hover:border-[#FF6B00] transition-all">
                  <span className="text-sm font-medium text-[#1E293B]">{n.skill_name}</span>
                  <span className="text-[#FF6B00] text-sm">Review →</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Weekly stats — plain language, no jargon here to begin with */}
        {stats.length > 0 && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 mb-8">
            <h2 className="font-bold text-[#1E293B] mb-4">This Week</h2>
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: 'Sessions', value: latestStats?.sessions_count || 0 },
                { label: 'Time (min)', value: Math.round(latestStats?.total_time_min || 0) },
                { label: 'Lessons Done', value: latestStats?.units_completed || 0 },
                { label: 'Avg Score', value: latestStats?.avg_quiz_score ? `${latestStats.avg_quiz_score.toFixed(0)}%` : '—' },
              ].map(item => (
                <div key={item.label} className="text-center p-3 bg-[#F8F9FC] rounded-xl">
                  <p className="text-2xl font-bold text-[#003087]">{item.value}</p>
                  <p className="text-xs text-[#64748B] mt-1">{item.label}</p>
                </div>
              ))}
            </div>
            {latestStats?.score_trend && (
              <div className="mt-3 flex items-center gap-2">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${latestStats.score_trend === 'improving' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                  {latestStats.score_trend === 'improving' ? '↑ Improving' : '→ Steady'}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Lesson-by-lesson mastery, not scroll depth */}
        <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
          <h2 className="font-bold text-[#1E293B] mb-4">Lesson Progress</h2>
          {nodes.length === 0 ? (
            <p className="text-[#94A3B8] text-sm text-center py-4">No progress yet. Start a lesson!</p>
          ) : (
            <div className="space-y-3">
              {nodes.map((n: any) => {
                const mastery = progressData?.bkt_mastery?.[n.node_id]
                if (mastery === undefined) return null
                const isMastered = progressData?.nodes_mastered?.includes(n.node_id)
                return (
                  <div key={n.node_id} className="flex items-center gap-4">
                    <span className="text-sm font-medium text-[#1E293B] w-48 truncate">{n.skill_name}</span>
                    <div className="flex-1 bg-[#E2E8F0] rounded-full h-2">
                      <div className={`h-2 rounded-full ${isMastered ? 'bg-[#22C55E]' : 'bg-[#003087]'}`}
                        style={{ width: `${Math.round(mastery * 100)}%` }}/>
                    </div>
                    <span className="text-xs text-[#94A3B8] w-16 text-right">
                      {isMastered ? '✓ Mastered' : `${Math.round(mastery * 100)}%`}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}