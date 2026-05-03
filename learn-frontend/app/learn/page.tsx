'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import { tracker } from '@/lib/tracker'
import Sidebar from '@/components/shared/Sidebar'
import CoachChat from '@/components/shared/CoachChat'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const LEVEL_NAMES: Record<number, string> = { 1: 'Foundation', 2: 'General', 3: 'Advanced', 4: 'Challenge' }
const LEVEL_COLORS: Record<number, string> = {
  1: 'bg-blue-100 text-blue-700',
  2: 'bg-green-100 text-green-700',
  3: 'bg-orange-100 text-orange-700',
  4: 'bg-red-100 text-red-700'
}
const CEFR_COLORS: Record<string, string> = { A1: 'bg-blue-50 text-blue-600', A2: 'bg-green-50 text-green-600', B1: 'bg-yellow-50 text-yellow-700', B2: 'bg-red-50 text-red-600' }

export default function LearnDashboard() {
  const router = useRouter()
  const [nodes, setNodes] = useState<any[]>([])
  const [progress, setProgress] = useState<any[]>([])
  const [profile, setProfile] = useState<any>(null)
  const [nodesMastered, setNodesMastered] = useState<string[]>([])
  const [currentGaps, setCurrentGaps] = useState<string[]>([])
  const [currentLevel, setCurrentLevel] = useState<string>('—')
  const [bktMastery, setBktMastery] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [pendingIntervention, setPendingIntervention] = useState<any>(null)
  const [popupVisible, setPopupVisible] = useState(false)
  const [interventionGaps, setInterventionGaps] = useState<string[]>([])
  const [abilityProjection, setAbilityProjection] = useState<any>(null)
  const [gapReview, setGapReview] = useState<any>(null)
  const [gapReviewLoading, setGapReviewLoading] = useState(false)
  const [coachOpen, setCoachOpen] = useState(false)
  const [coachIntervention, setCoachIntervention] = useState<string | null>(null)

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      const sessionId = localStorage.getItem('session_id')
      if (sessionId) tracker.setSessionId(sessionId)
      try {
        const [nodesRes, progressRes, profileRes, masteryRes, interventionRes] = await Promise.all([
          api.get('/content/nodes'),
          api.get('/content/progress'),
          api.get('/profile/me'),
          api.get('/profile/progress'),
          api.get('/profile/pending-intervention'),
        ])
        setNodes(nodesRes.data)
        setProgress(progressRes.data)
        setProfile(profileRes.data)
        setNodesMastered(masteryRes.data.nodes_mastered || [])
        setBktMastery(masteryRes.data.bkt_mastery || {})
        setCurrentGaps(masteryRes.data.current_gaps || [])
        setCurrentLevel(masteryRes.data.current_level || profileRes.data.self_reported_level || '—')
        if (interventionRes.data) {
          setPendingIntervention(interventionRes.data)
          setTimeout(() => setPopupVisible(true), 300)  // small delay so it feels like it "arrives", not a jarring instant popup

          // Resolve gap node_ids to real skill names, using the nodes we already fetched
          const gapNames = (masteryRes.data.current_gaps || []).map(
            (id: string) => nodesRes.data.find((n: any) => n.node_id === id)?.skill_name || id
          )
          setInterventionGaps(gapNames)

          // Fetch the projection lazily — only when there's actually a
          // popup to show it on, not on every dashboard load
          try {
            const proj = await api.get('/profile/ability-projection', { params: { band: 'easy', count: 10 } })
            setAbilityProjection(proj.data)
          } catch { /* projection is a nice-to-have — popup still works without it */ }
        }
      } catch (err) {
        console.error('Failed to load learn dashboard data:', err)
      }
      setLoading(false)
    }
    init()
  }, [router])

  const dismissIntervention = async () => {
    setPopupVisible(false)
    if (pendingIntervention) {
      try {
        await api.post('/profile/intervention-viewed', { intervention_id: pendingIntervention.intervention_id })
      } catch {}
    }
    setTimeout(() => setPendingIntervention(null), 200)  // let the fade-out finish first
  }

  const openGapReview = async (nodeId: string) => {
    setGapReviewLoading(true)
    setGapReview({ node_id: nodeId })
    try {
      const res = await api.get('/profile/gap-review', { params: { node_id: nodeId } })
      setGapReview(res.data)
    } catch (err) {
      setGapReview({ node_id: nodeId, error: true })
    }
    setGapReviewLoading(false)
  }

  const getNodeProgress = (nodeId: string) => progress.find(p => p.node_id === nodeId)
  const completedCount = progress.filter(p => p.completed).length

  // A node is unlocked once every one of its prerequisites has actually
  // been mastered — no prerequisites means it's open from the start.
  const isNodeLocked = (node: any) => {
    const prereqs: string[] = node.prerequisites || []
    return prereqs.some(p => !nodesMastered.includes(p))
  }
  const missingPrereqNames = (node: any) => {
    const prereqs: string[] = node.prerequisites || []
    return prereqs
      .filter(p => !nodesMastered.includes(p))
      .map(p => nodes.find(n => n.node_id === p)?.skill_name || p)
  }
  const MASTERY_THRESHOLD = 0.95  // matches the backend's actual unlock rule
  const missingPrereqDetails = (node: any) => {
    const prereqs: string[] = node.prerequisites || []
    return prereqs
      .filter(p => !nodesMastered.includes(p))
      .map(p => ({
        name: nodes.find(n => n.node_id === p)?.skill_name || p,
        current: Math.round((bktMastery[p] ?? 0) * 100),
        required: Math.round(MASTERY_THRESHOLD * 100),
      }))
  }
  const progressLabel = (mastery: number) => {
    if (mastery >= 0.95) return 'Mastered'
    if (mastery >= 0.5) return 'Going well'
    if (mastery > 0) return 'Just started'
    return 'Not started'
  }
  const byLevel = [1, 2, 3, 4].map(l => ({ level: l, nodes: nodes.filter(n => n.level === l) }))

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
      <Sidebar userName={profile?.email?.split('@')[0] || ''} />

      {/* Dropout intervention popup — a warm check-in, not a data dump */}
      {pendingIntervention && (
        <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black/40 transition-opacity duration-300 ${popupVisible ? 'opacity-100' : 'opacity-0'}`}>
          <div className={`bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 p-8 text-center transition-all duration-300 ${popupVisible ? 'scale-100 opacity-100' : 'scale-90 opacity-0'}`}>
            <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-5 text-3xl">
              👋
            </div>
            <h3 className="text-lg font-bold text-[#1E293B] mb-3">Welcome back!</h3>
            <p className="text-[#475569] text-sm leading-relaxed mb-5">{pendingIntervention.message_sent}</p>

            {interventionGaps.length > 0 && (
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-left">
                <p className="text-xs font-semibold text-[#FF6B00] uppercase tracking-wide mb-2">Worth revisiting</p>
                <div className="flex flex-wrap gap-2">
                  {interventionGaps.slice(0, 3).map(name => (
                    <span key={name} className="text-xs font-medium bg-white border border-orange-200 text-[#1E293B] px-2.5 py-1 rounded-full">{name}</span>
                  ))}
                </div>
              </div>
            )}

            {abilityProjection && abilityProjection.delta > 0 && (
              <div className="bg-[#EFF6FF] border border-blue-200 rounded-xl p-4 mb-6 text-left">
                <p className="text-xs font-semibold text-[#003087] uppercase tracking-wide mb-1">A small, concrete step</p>
                <p className="text-sm text-[#1E293B]">
                  Get <span className="font-semibold">{abilityProjection.count} easy questions</span> right this week, and your ability score moves up by roughly <span className="font-semibold text-[#22C55E]">+{(abilityProjection.delta / 8 * 100).toFixed(0)}%</span> of the full scale — a real, visible step forward.
                </p>
              </div>
            )}

            <button
              onClick={dismissIntervention}
              className="w-full bg-[#003087] hover:bg-[#0047c8] text-white font-semibold py-3 rounded-xl transition-all"
            >
              Let's go!
            </button>
            <button
              onClick={() => {
                const iid = pendingIntervention?.intervention_id || null
                dismissIntervention()
                setCoachIntervention(iid)
                setCoachOpen(true)
              }}
              className="w-full mt-2 border border-[#003087] text-[#003087] hover:bg-[#EFF6FF] font-semibold py-3 rounded-xl transition-all"
            >
              💬 Talk it through with your coach
            </button>
          </div>
        </div>
      )}

      {/* LEARN Coach: chat about real progress (opened from the check-in or the button) */}
      <CoachChat open={coachOpen} onClose={() => setCoachOpen(false)} interventionId={coachIntervention} />
      {!coachOpen && (
        <button
          onClick={() => { setCoachIntervention(null); setCoachOpen(true) }}
          className="fixed bottom-6 right-6 z-40 bg-[#003087] hover:bg-[#0047c8] text-white font-semibold px-5 py-3 rounded-full shadow-lg flex items-center gap-2"
          aria-label="Open LEARN Coach"
        >
          💬 Coach
        </button>
      )}

      {/* Gap review modal — the actual content-generation piece, not just a nudge */}
      {gapReview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setGapReview(null)}>
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full mx-4 p-6" onClick={e => e.stopPropagation()}>
            {gapReviewLoading ? (
              <div className="text-center py-8">
                <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin mx-auto mb-3"/>
                <p className="text-sm text-[#94A3B8]">Putting together a quick review...</p>
              </div>
            ) : gapReview.error ? (
              <div className="text-center py-6">
                <p className="text-sm text-[#94A3B8] mb-4">Couldn't generate a review right now — try again in a moment.</p>
                <button onClick={() => setGapReview(null)} className="text-sm text-[#003087] font-medium">Close</button>
              </div>
            ) : (
              <>
                <p className="text-xs font-semibold text-[#FF6B00] uppercase tracking-wide mb-1">Quick Review</p>
                <h3 className="text-lg font-bold text-[#1E293B] mb-4">{gapReview.skill_name}</h3>
                <p className="text-sm text-[#475569] leading-relaxed mb-4">{gapReview.explanation}</p>
                {gapReview.visual_aid_markdown && (
                  <div className="mb-4 bg-[#F8F9FC] border border-[#E2E8F0] rounded-xl p-4 text-sm overflow-x-auto">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        table: ({ ...props }) => <table className="border-collapse w-full" {...props} />,
                        th: ({ ...props }) => <th className="border border-[#E2E8F0] bg-white px-3 py-1.5 text-left font-semibold text-[#1E293B]" {...props} />,
                        td: ({ ...props }) => <td className="border border-[#E2E8F0] px-3 py-1.5 text-[#475569]" {...props} />,
                      }}
                    >
                      {gapReview.visual_aid_markdown}
                    </ReactMarkdown>
                  </div>
                )}
                <Link
                  href={`/learn/${gapReview.node_id}/quiz`}
                  className="block w-full bg-[#003087] hover:bg-[#0047c8] text-white font-semibold py-3 rounded-xl text-center transition-all"
                >
                  Practice Now →
                </Link>
              </>
            )}
          </div>
        </div>
      )}

      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] p-8">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#1E293B]">
            Hello, {profile?.email?.split('@')[0]} 👋
          </h1>
          <p className="text-[#64748B] mt-1">Continue your English learning journey</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: 'Lessons Completed', value: completedCount, total: nodes.length, icon: '📚', color: 'text-[#003087]', bg: 'bg-blue-50' },
            { label: 'Current Level', value: currentLevel, icon: '🎯', color: 'text-[#FF6B00]', bg: 'bg-orange-50' },
            { label: 'VARK Style', value: profile?.vark_label ? `${profile.vark_label} Type` : 'Pending', icon: '🧠', color: 'text-purple-600', bg: 'bg-purple-50' },
          ].map(stat => (
            <div key={stat.label} className="bg-white rounded-xl border border-[#E2E8F0] p-5">
              <div className={`w-10 h-10 ${stat.bg} rounded-lg flex items-center justify-center mb-3`}>
                <span>{stat.icon}</span>
              </div>
              <p className={`text-xl font-bold ${stat.color} capitalize`}>
                {typeof stat.value === 'number' ? `${stat.value}${stat.total ? ` / ${stat.total}` : ''}` : stat.value}
              </p>
              <p className="text-sm text-[#64748B] mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* Overall progress bar */}
        <div className="bg-white rounded-xl border border-[#E2E8F0] p-5 mb-8">
          <div className="flex items-center justify-between mb-2">
            <p className="font-semibold text-[#1E293B]">Overall Progress</p>
            <p className="text-sm text-[#64748B]">{completedCount} of {nodes.length} lessons</p>
          </div>
          <div className="w-full bg-[#E2E8F0] rounded-full h-3">
            <div className="bg-[#003087] h-3 rounded-full transition-all duration-500"
              style={{ width: nodes.length ? `${(completedCount / nodes.length) * 100}%` : '0%' }}/>
          </div>
        </div>

        {/* Nodes by level */}
        {byLevel.map(({ level, nodes: levelNodes }) => levelNodes.length > 0 && (
          <div key={level} className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <span className={`text-xs font-bold px-3 py-1 rounded-full ${LEVEL_COLORS[level]}`}>
                LEVEL {level}
              </span>
              <h2 className="font-bold text-[#1E293B]">{LEVEL_NAMES[level]}</h2>
              <div className="flex-1 h-px bg-[#E2E8F0]"/>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {levelNodes.map((node: any) => {
                const prog = getNodeProgress(node.node_id)
                const isCompleted = prog?.completed
                const isActive = profile?.current_active_node === node.node_id
                const locked = isNodeLocked(node)
                const mastery = bktMastery[node.node_id] ?? 0
                const lessonNumber = nodes.findIndex(n => n.node_id === node.node_id) + 1

                const cardBody = (
                  <div className={`rounded-xl border-2 p-5 transition-all ${
                    locked
                      ? 'bg-[#F8F9FC] border-[#E2E8F0] opacity-60 cursor-not-allowed'
                      : `bg-white cursor-pointer hover:shadow-md hover:-translate-y-0.5 ${isActive ? 'border-[#003087]' : isCompleted ? 'border-[#22C55E]' : 'border-[#E2E8F0]'}`
                  }`}>
                    <div className="flex items-start justify-between mb-3">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${CEFR_COLORS[node.cefr_level] || 'bg-gray-100 text-gray-600'}`}>
                        {node.cefr_level}
                      </span>
                      <div className="flex items-center gap-1">
                        {locked ? (
                          <span className="text-sm">🔒</span>
                        ) : (
                          <>
                            {currentGaps.includes(node.node_id) && (
                              <button
                                onClick={(e) => { e.preventDefault(); e.stopPropagation(); openGapReview(node.node_id) }}
                                title="This is a current gap — get a quick AI review"
                                className="text-xs bg-orange-100 hover:bg-orange-200 text-[#FF6B00] font-semibold px-2 py-0.5 rounded-full"
                              >
                                💡 Review
                              </button>
                            )}
                            {node.has_video && <span className="text-xs">🎬</span>}
                            {node.has_audio && <span className="text-xs">🎧</span>}
                            {isCompleted && <span className="text-green-500 text-sm">✓</span>}
                            {isActive && !isCompleted && <span className="w-2 h-2 bg-[#003087] rounded-full"/>}
                          </>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-[#94A3B8] font-medium mb-1">Lesson {lessonNumber}</p>
                    <p className="font-semibold text-[#1E293B] text-sm mb-3">{node.skill_name}</p>

                    {locked ? (
                      <p className="text-xs text-[#94A3B8] italic">
                        Unlocks after: {missingPrereqNames(node).join(', ')}
                      </p>
                    ) : (
                      <>
                        <div className="w-full bg-[#E2E8F0] rounded-full h-1.5 mb-1.5">
                          <div className="bg-[#003087] h-1.5 rounded-full transition-all duration-500"
                            style={{ width: `${Math.round(mastery * 100)}%` }}/>
                        </div>
                        <div className="flex items-center justify-between">
                          <p className="text-xs text-[#64748B]">{progressLabel(mastery)}</p>
                          {node.estimated_minutes && <span className="text-xs text-[#94A3B8]">⏱ {node.estimated_minutes} min</span>}
                        </div>
                      </>
                    )}
                  </div>
                )

                return locked ? (
                  <div key={node.node_id} className="group relative">
                    {cardBody}
                    <div className="absolute left-0 right-0 top-full mt-2 z-30 bg-[#1E293B] text-white text-xs rounded-xl p-4 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 shadow-xl">
                      <p className="font-semibold mb-2">To unlock this lesson:</p>
                      <div className="space-y-2">
                        {missingPrereqDetails(node).map(d => (
                          <div key={d.name}>
                            <div className="flex items-center justify-between mb-1">
                              <span>{d.name}</span>
                              <span className="text-[#94A3B8]">{d.current}% / {d.required}%</span>
                            </div>
                            <div className="w-full bg-white/20 rounded-full h-1.5">
                              <div className="bg-[#FF6B00] h-1.5 rounded-full" style={{ width: `${Math.min(100, (d.current / d.required) * 100)}%` }}/>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <Link key={node.node_id} href={`/learn/${node.node_id}`}>{cardBody}</Link>
                )
              })}
            </div>
          </div>
        ))}

        {nodes.length === 0 && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-12 text-center">
            <p className="text-4xl mb-4">📚</p>
            <p className="font-semibold text-[#1E293B] mb-2">No lessons available yet</p>
            <p className="text-[#64748B] text-sm">Content is being prepared. Check back soon.</p>
          </div>
        )}
      </main>
    </div>
  )
}