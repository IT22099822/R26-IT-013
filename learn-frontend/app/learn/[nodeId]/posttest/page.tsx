'use client'
import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import AnchorScreen from '@/components/quiz/AnchorScreen'
import Sidebar from '@/components/shared/Sidebar'

export default function PostTestPage() {
  const router = useRouter()
  const { nodeId } = useParams()
  const [questions, setQuestions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [generationFailed, setGenerationFailed] = useState(false)
  const [summary, setSummary] = useState<any>(null)
  const sessionId = typeof window !== 'undefined' ? localStorage.getItem('session_id') || '' : ''

  const loadQuestions = async () => {
    setLoading(true)
    setGenerationFailed(false)
    setSummary(null)
    try {
      const res = await api.get(`/quiz/${nodeId}/anchor?test_type=post`)
      if (res.data.generation_failed) {
        setGenerationFailed(true)
      } else if (res.data.questions.length === 0) {
        router.push(`/learn/${nodeId}`)
        return
      } else {
        setQuestions(res.data.questions)
      }
    } catch {
      router.push(`/learn/${nodeId}`)
    }
    setLoading(false)
  }

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      await loadQuestions()
    }
    init()
  }, [nodeId, router])

  // summary carries: score_pct, correct_count, total_questions, mastery,
  // is_mastered, newly_unlocked, message, attempt_number, feedback —
  // feedback is only present for retakes (attempt_number > 1), since
  // attempt 1 uses the real calibrated pool and stays feedback-free on
  // purpose (protects the IRT calibration that pool is used for).
  const handleComplete = (result?: any) => {
    if (result && result.score_pct !== undefined) {
      setSummary(result)
    } else {
      router.push('/learn')
    }
  }

  if (loading) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
      </main>
    </div>
  )

  if (generationFailed) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 max-w-sm w-full text-center">
          <div className="w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">⚠️</span>
          </div>
          <h2 className="text-lg font-bold text-[#1E293B] mb-2">Couldn't generate new questions</h2>
          <p className="text-sm text-[#64748B] mb-6">Something went wrong preparing this retake. Please try again.</p>
          <button
            onClick={loadQuestions}
            className="w-full bg-[#003087] text-white font-semibold py-3 rounded-xl hover:bg-[#0047c8] transition-all"
          >
            Try Again
          </button>
        </div>
      </main>
    </div>
  )

  // ── Module completion summary ──
  if (summary) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] p-8">
        <div className="max-w-lg mx-auto">
          <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 mb-4">
            {(() => {
              // Mastered from prior practice AND this specific attempt
              // actually supports celebrating — not just the standing
              // fact alone. A student who just scored 0% shouldn't see
              // "Lesson Mastered!" even if earlier practice was strong;
              // that mismatch is exactly the confusing, dishonest-looking
              // combination this screen used to produce.
              const celebrateThisAttempt = summary.is_mastered && summary.score_pct >= 50
              return (
                <div className="text-center mb-6">
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${celebrateThisAttempt ? 'bg-green-100' : 'bg-blue-100'}`}>
                    <span className="text-4xl">{celebrateThisAttempt ? '🎉' : '📘'}</span>
                  </div>
                  <h2 className="text-xl font-bold text-[#1E293B] mb-1">
                    {celebrateThisAttempt ? "Lesson Mastered!" : "Post-test Complete"}
                  </h2>
                  <p className="text-[#64748B] text-sm">You scored {summary.score_pct}% ({summary.correct_count}/{summary.total_questions})</p>
                  {summary.attempt_number > 1 && (
                    <p className="text-xs text-[#94A3B8] mt-1">Attempt {summary.attempt_number} — fresh questions each time</p>
                  )}
                </div>
              )
            })()}

            <div className="mb-6">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wide">Mastery of this lesson</span>
                <span className="text-xs font-bold text-[#003087]">{Math.round((summary.mastery || 0) * 100)}%</span>
              </div>
              <div className="w-full bg-[#E2E8F0] rounded-full h-2.5">
                <div className={`h-2.5 rounded-full transition-all duration-700 ${summary.is_mastered ? 'bg-[#22C55E]' : 'bg-[#003087]'}`}
                  style={{ width: `${Math.round((summary.mastery || 0) * 100)}%` }}/>
              </div>
            </div>

            {summary.message && (
              <div className="bg-[#EFF6FF] border border-blue-200 rounded-xl p-4 mb-6 flex gap-3">
                <span className="text-xl">🧭</span>
                <p className="text-sm text-[#1E293B] leading-relaxed">{summary.message}</p>
              </div>
            )}

            {summary.newly_unlocked && summary.newly_unlocked.length > 0 && (
              <div className="mb-6">
                <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wide mb-2">Newly Unlocked</p>
                <div className="flex flex-wrap gap-2">
                  {summary.newly_unlocked.map((name: string) => (
                    <span key={name} className="text-sm font-medium bg-orange-50 border border-orange-200 text-[#FF6B00] px-3 py-1.5 rounded-full">
                      🔓 {name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={loadQuestions}
                className="flex-1 bg-[#FF6B00] hover:bg-orange-600 text-white font-semibold py-3.5 rounded-xl transition-all"
              >
                Take It Again
              </button>
              <button
                onClick={() => router.push('/learn')}
                className="flex-1 bg-[#003087] hover:bg-[#0047c8] text-white font-semibold py-3.5 rounded-xl transition-all"
              >
                Back to Dashboard
              </button>
            </div>
          </div>

          {/* Per-question review — only ever present on retakes, since
              attempt 1 stays feedback-free by design */}
          {summary.feedback && summary.feedback.length > 0 && (
            <div className="bg-white rounded-2xl border border-[#E2E8F0] p-6">
              <h3 className="font-bold text-[#1E293B] mb-4">Review Your Answers</h3>
              <div className="space-y-4">
                {summary.feedback.map((f: any, i: number) => (
                  <div key={f.question_id} className={`rounded-xl p-4 border ${f.correct ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-[#94A3B8] uppercase">Question {i + 1}</span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${f.correct ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                        {f.correct ? '✓ Correct' : '✗ Incorrect'}
                      </span>
                    </div>
                    {!f.correct && (
                      <p className="text-sm text-[#475569] mb-2">
                        You chose <span className="font-semibold">{f.selected_option}</span> — the correct answer was <span className="font-semibold text-green-700">{f.correct_option}</span>
                      </p>
                    )}
                    {f.explanation && (
                      <p className="text-sm text-[#64748B] italic">{f.explanation}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )

  return (
    <AnchorScreen
      questions={questions}
      nodeId={nodeId as string}
      testType="post"
      sessionId={sessionId}
      onComplete={handleComplete}
    />
  )
}