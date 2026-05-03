'use client'
import { useEffect, useState, useRef } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import { tracker } from '@/lib/tracker'
import Sidebar from '@/components/shared/Sidebar'
import AnchorScreen from '@/components/quiz/AnchorScreen'  // ← NEW
import LearningGuide from '@/components/shared/LearningGuide'

const VARK_INFO: Record<string, { label: string; icon: string; desc: string }> = {
  V: { label: 'Visual', icon: '👁️', desc: 'you learn best through images and video' },
  A: { label: 'Auditory', icon: '👂', desc: 'you learn best through listening' },
  R: { label: 'Reading & Writing', icon: '📝', desc: 'you learn best through reading' },
  K: { label: 'Hands-on', icon: '✋', desc: 'you learn best through practice' },
}

export default function LessonPage() {
  const router = useRouter()
  const { nodeId } = useParams()
  const [node, setNode] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const audioRef = useRef<HTMLAudioElement>(null)
  const textDetailsRef = useRef<HTMLDetailsElement>(null)
  // ← NEW: anchor gate state
  const [anchorReady, setAnchorReady] = useState(false)
  const [anchorQuestions, setAnchorQuestions] = useState<any[]>([])
  const [mastery, setMastery] = useState(0)
  const [varkLabel, setVarkLabel] = useState<string | null>(null)
  const sessionId = typeof window !== 'undefined' ? localStorage.getItem('session_id') || '' : ''

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      const sessionId = localStorage.getItem('session_id')
      if (sessionId) tracker.setSessionId(sessionId)
      try {
        const [nodeRes, anchorRes, progressRes, profileRes] = await Promise.all([
          api.get(`/content/node/${nodeId}`),
          api.get(`/quiz/${nodeId}/anchor?test_type=pre`),  // ← NEW
          api.get('/profile/progress'),
          api.get('/profile/me'),
        ])
        setNode(nodeRes.data)
        setMastery(progressRes.data.bkt_mastery?.[nodeId as string] ?? 0)
        // Onboarding (questionnaire) label shown here on purpose, per
        // design — the behavioral label evolves quietly in the
        // background via the weekly classifier and shows up in the
        // admin view and My Progress page, not as the headline here.
        setVarkLabel(profileRes.data.vark_questionnaire_label)

        // ← NEW: if already done or no anchor questions, skip gate
        if (anchorRes.data.already_done || anchorRes.data.questions.length === 0) {
          setAnchorReady(true)
        } else {
          setAnchorQuestions(anchorRes.data.questions)
          // anchorReady stays false → AnchorScreen renders first
        }

        tracker.log('unit_open', nodeId as string, 0)
        // Scroll tracking is now gated on the reading section actually
        // being open — see the dedicated useEffect below. Starting it
        // here unconditionally was the bug: scrolling past a COLLAPSED
        // reading section was being counted as reading engagement,
        // corrupting the exact scroll_depth_pct feature the VARK
        // classifier trains and predicts on.
      } catch { router.push('/learn') }
      setLoading(false)
    }
    init().then(() => setLoading(false))
  }, [nodeId, router])

  useEffect(() => {
    if (node?.has_audio && audioRef.current) {
      tracker.initAudioTracking(audioRef.current, nodeId as string)
    }
  }, [node, nodeId])

  // Scroll tracking gated on the reading section's REAL open state —
  // this is the actual fix. Previously it ran unconditionally from
  // page load, meaning scrolling past a collapsed reading section
  // silently counted as reading engagement, corrupting the exact
  // scroll_depth_pct signal the VARK classifier trains on.
  useEffect(() => {
    const el = textDetailsRef.current
    if (!el) return
    let cleanupScroll: (() => void) | null = null

    const startIfOpen = () => {
      if (el.open && !cleanupScroll) {
        cleanupScroll = tracker.initScrollTracking(nodeId as string)
      } else if (!el.open && cleanupScroll) {
        cleanupScroll()
        cleanupScroll = null
      }
    }

    startIfOpen()  // handles the case where it's open by default (R-type student)
    el.addEventListener('toggle', startIfOpen)  // handles manual expand/collapse

    return () => {
      el.removeEventListener('toggle', startIfOpen)
      if (cleanupScroll) cleanupScroll()
    }
  }, [node, nodeId])

  if (loading || !node) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
      </main>
    </div>
  )

  // ← NEW: show anchor screen before lesson content
  if (!anchorReady && anchorQuestions.length > 0) {
    return (
      <AnchorScreen
        questions={anchorQuestions}
        nodeId={nodeId as string}
        testType="pre"
        sessionId={sessionId}
        onComplete={() => setAnchorReady(true)}
      />
    )
  }

  // ── Everything below is your ORIGINAL code, unchanged ──────────────────────

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC]">
        <div className="bg-white border-b border-[#E2E8F0] px-8 py-4 flex items-center gap-4 sticky top-0 z-10">
          <Link href="/learn" className="text-[#64748B] hover:text-[#003087] text-sm flex items-center gap-1.5 font-medium">
            ← Back
          </Link>
          <div className="h-4 w-px bg-[#E2E8F0]"/>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${node.level === 1 ? 'bg-blue-100 text-blue-700' : node.level === 2 ? 'bg-green-100 text-green-700' : node.level === 3 ? 'bg-orange-100 text-orange-700' : 'bg-red-100 text-red-700'}`}>
              Level {node.level}
            </span>
            <span className="text-sm text-[#64748B]">{node.cefr_level}</span>
            <span className="text-sm font-semibold text-[#1E293B]">· {node.node_id}</span>
          </div>
          {node.estimated_minutes && (
            <span className="ml-auto text-sm text-[#94A3B8]">⏱ {node.estimated_minutes} min</span>
          )}
        </div>

        <div className="max-w-3xl mx-auto px-8 py-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-[#1E293B] mb-3">{node.skill_name}</h1>
            {node.summary && <p className="text-[#64748B] text-lg leading-relaxed">{node.summary}</p>}
          </div>

          {/* How to master this lesson — templated guidance from current mastery */}
          <div className={`rounded-xl p-5 mb-8 border ${mastery >= 0.95 ? 'bg-green-50 border-green-200' : 'bg-[#EFF6FF] border-blue-200'}`}>
            <div className="flex items-start gap-3">
              <span className="text-2xl">{mastery >= 0.95 ? '🎉' : mastery > 0 ? '💪' : '👋'}</span>
              <div className="flex-1">
                <p className="font-semibold text-[#1E293B] mb-1">
                  {mastery >= 0.95
                    ? "You've mastered this lesson!"
                    : mastery > 0
                    ? "You're making progress"
                    : "Let's get started"}
                </p>
                <p className="text-sm text-[#475569]">
                  {mastery >= 0.95
                    ? "Feel free to review the material anytime, or head back to keep moving through your lessons."
                    : mastery > 0
                    ? `You're ${Math.round(mastery * 100)}% of the way there. A bit more practice below will help it stick.`
                    : "Read through the lesson below, then complete the practice quiz to start building your mastery."}
                </p>
                {mastery > 0 && mastery < 0.95 && (
                  <div className="w-full bg-white/60 rounded-full h-1.5 mt-3 max-w-xs">
                    <div className="bg-[#003087] h-1.5 rounded-full transition-all duration-500" style={{ width: `${Math.round(mastery * 100)}%` }}/>
                  </div>
                )}
              </div>
            </div>
          </div>

          {node.learning_objectives && node.learning_objectives.length > 0 && (
            <div className="bg-[#EFF6FF] border border-blue-200 rounded-xl p-5 mb-8">
              <p className="font-semibold text-[#003087] mb-3 flex items-center gap-2">
                <span>🎯</span> Learning Objectives
              </p>
              <ul className="space-y-2">
                {node.learning_objectives.map((obj: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#1E293B]">
                    <span className="text-[#003087] font-bold mt-0.5">✦</span> {obj}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* "Learn the way you prefer" banner — shows the ONBOARDING
              VARK label. The format matching it opens first below;
              everything else stays present, just collapsed, so the
              student can always explore other formats — that's what
              lets the behavioral classifier pick up real signal over
              time instead of only ever seeing one format. */}
          {varkLabel && VARK_INFO[varkLabel] && (
            <div className="bg-gradient-to-r from-[#EFF6FF] to-white border border-blue-200 rounded-xl p-4 mb-6 flex items-center gap-3">
              <span className="text-2xl">{VARK_INFO[varkLabel].icon}</span>
              <div>
                <p className="font-semibold text-[#1E293B] text-sm">Learn the way you prefer</p>
                <p className="text-xs text-[#64748B]">
                  Based on your onboarding, {VARK_INFO[varkLabel].desc} — that's opened first below, but every format is here if you want to try something different.
                </p>
              </div>
            </div>
          )}

          {(() => {
            const sections: { key: string; vark: string; el: React.ReactNode }[] = []
            if (node.has_video && node.video_youtube_id) {
              sections.push({
                key: 'video', vark: 'V', el: (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-lg">🎬</span>
                      <p className="font-semibold text-[#1E293B]">Video Lesson</p>
                    </div>
                    <div className="rounded-xl overflow-hidden shadow-md aspect-video bg-black">
                      <iframe
                        width="100%" height="100%"
                        src={`https://www.youtube.com/embed/${node.video_youtube_id}?enablejsapi=1`}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                        className="w-full h-full"
                        onLoad={() => tracker.log('video_play', nodeId as string, 0)}
                      />
                    </div>
                  </div>
                )
              })
            }
            if (node.lesson_markdown) {
              sections.push({
                key: 'text', vark: 'R', el: (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-lg">📝</span>
                      <p className="font-semibold text-[#1E293B]">Reading</p>
                    </div>
                    <div className="prose max-w-none">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: ({ ...props }) => <table className="border-collapse w-full my-3" {...props} />,
                          th: ({ ...props }) => <th className="border border-[#E2E8F0] bg-[#F8F9FC] px-3 py-1.5 text-left font-semibold text-[#1E293B]" {...props} />,
                          td: ({ ...props }) => <td className="border border-[#E2E8F0] px-3 py-1.5 text-[#475569]" {...props} />,
                        }}
                      >
                        {node.lesson_markdown}
                      </ReactMarkdown>
                    </div>
                  </div>
                )
              })
            }
            if (node.has_audio && node.audio_file_url) {
              sections.push({
                key: 'audio', vark: 'A', el: (
                  <div>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-[#EFF6FF] rounded-lg flex items-center justify-center">
                        <span>🎧</span>
                      </div>
                      <div>
                        <p className="font-semibold text-[#1E293B] text-sm">Audio Lesson</p>
                        <p className="text-xs text-[#94A3B8]">Listen to reinforce your learning</p>
                      </div>
                    </div>
                    <audio ref={audioRef} controls className="w-full rounded-lg" src={node.audio_file_url}/>
                  </div>
                )
              })
            }

            // Preferred format first; a K-type student has no matching
            // passive format, so everything stays collapsed for them
            // and the practice CTA below is where they're meant to go.
            const ordered = [...sections].sort((a, b) => {
              if (a.vark === varkLabel) return -1
              if (b.vark === varkLabel) return 1
              return 0
            })
            const hasMatch = ordered.some(s => s.vark === varkLabel)

            return (
              <>
                {varkLabel === 'K' && (
                  <div className="bg-[#003087] rounded-xl p-5 mb-6 text-white flex items-center justify-between">
                    <div>
                      <p className="font-bold">Prefer to learn by doing?</p>
                      <p className="text-sm text-blue-200">Jump straight to practice — you can always come back to the material below.</p>
                    </div>
                    {node.questions_ready && (
                      <Link href={`/learn/${nodeId}/quiz`}>
                        <button className="bg-[#FF6B00] hover:bg-orange-600 text-white font-semibold py-2.5 px-6 rounded-xl transition-all whitespace-nowrap">
                          Practice →
                        </button>
                      </Link>
                    )}
                  </div>
                )}
                {ordered.map((s, i) => (
                  <details
                    key={s.key}
                    ref={s.key === 'text' ? textDetailsRef : undefined}
                    open={hasMatch ? s.vark === varkLabel : i === 0}
                    className="bg-white rounded-xl border border-[#E2E8F0] p-6 mb-4 group"
                  >
                    <summary className="cursor-pointer list-none flex items-center justify-between">
                      <span className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wide">
                        {s.vark === varkLabel ? '⭐ Your preferred format' : 'Also available'}
                      </span>
                      <span className="text-[#94A3B8] text-sm group-open:rotate-180 transition-transform">▾</span>
                    </summary>
                    <div className="mt-4">{s.el}</div>
                  </details>
                ))}
              </>
            )
          })()}

          {node.questions_ready ? (
            <div className="bg-[#003087] rounded-xl p-6 text-white text-center">
              <p className="text-xl font-bold mb-2">Ready to test yourself?</p>
              <p className="text-blue-200 mb-5 text-sm">Take the quiz for this lesson to check your understanding.</p>
              <Link href={`/learn/${nodeId}/quiz`}>
                <button className="bg-[#FF6B00] hover:bg-orange-600 text-white font-semibold py-3 px-8 rounded-xl transition-all">
                  Take Quiz →
                </button>
              </Link>
            </div>
          ) : (
            <div className="bg-[#F8F9FC] border border-[#E2E8F0] rounded-xl p-6 text-center">
              <p className="text-[#64748B] text-sm">Quiz for this lesson is being prepared. Check back soon.</p>
              <Link href="/learn">
                <button className="mt-3 text-[#003087] font-semibold text-sm hover:underline">← Back to Dashboard</button>
              </Link>
            </div>
          )}
        </div>
      </main>
      <LearningGuide nodeId={nodeId as string} />
    </div>
  )
}