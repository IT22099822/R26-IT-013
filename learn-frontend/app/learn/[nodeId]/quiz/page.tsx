'use client'
import { useEffect, useState, useRef, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import { tracker } from '@/lib/tracker'
import Sidebar from '@/components/shared/Sidebar'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function QuizPage() {
  const router = useRouter()
  const { nodeId } = useParams()

  const [mode, setMode] = useState<'choosing' | 'loading' | 'ready' | 'generation_failed'>('choosing')
  const [questions, setQuestions] = useState<any[]>([])
  const [result, setResult] = useState<any>(null)
  const [submitting, setSubmitting] = useState(false)

  // Difficulty badge — now computed server-side, RELATIVE to this
  // student's actual ability (same question can be "easy" for one
  // student and "hard" for another). difficulty_tag == 0 still means
  // "never assigned" in this content bank, so that stays an honest
  // "Not yet rated" rather than a guessed label.
  const getDifficultyBadge = (relativeDifficulty: string | undefined) => {
    switch (relativeDifficulty) {
      case 'easy': return { label: 'Easy for you', className: 'bg-green-100 text-green-700' }
      case 'medium': return { label: 'Just right', className: 'bg-yellow-100 text-yellow-700' }
      case 'hard': return { label: 'Challenging', className: 'bg-red-100 text-red-700' }
      default: return { label: 'Not yet rated', className: 'bg-gray-100 text-gray-500' }
    }
  }

  // selected option per question index
  const [selected, setSelected] = useState<Record<number, string>>({})
  // submitted (answered + API called) per question index
  const [submitted, setSubmitted] = useState<Record<number, boolean>>({})
  // answer results (correct/incorrect) per question index
  const [answerResults, setAnswerResults] = useState<Record<number, { correct: boolean; correct_option: string }>>({})

  // time tracking: when student first taps/sees each question
  // key = question index, value = timestamp ms
  const focusedAt = useRef<Record<number, number>>({})
  // track if they've already focused this question (prevent reset on re-render)
  const hasFocused = useRef<Record<number, boolean>>({})

  // intersection observer refs per question card
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])

  const sessionId = typeof window !== 'undefined' ? localStorage.getItem('session_id') || '' : ''

  const loadStandardPractice = async () => {
    setMode('loading')
    try {
      const res = await api.get(`/quiz/${nodeId}`)
      if (!res.data.ready) {
        console.warn('Quiz not ready for this node (backend returned ready=false):', nodeId)
        router.push(`/learn/${nodeId}`); return
      }
      setQuestions(res.data.questions)
      tracker.log('quiz_start', nodeId as string, 0)
      setMode('ready')
    } catch (err) {
      console.error('Failed to load quiz for node', nodeId, ':', err)
      router.push(`/learn/${nodeId}`)
    }
  }

  // On-demand practice at a difficulty the student picks themselves —
  // relative to THEIR ability, not a fixed universal difficulty.
  const requestCustomDifficulty = async (band: string) => {
    setMode('loading')
    try {
      const res = await api.post(`/quiz/${nodeId}/practice-request`, { difficulty_band: band, count: 5 })
      if (res.data.generation_failed || res.data.questions.length === 0) {
        setMode('generation_failed')
        return
      }
      setQuestions(res.data.questions)
      tracker.log('quiz_start', nodeId as string, 0)
      setMode('ready')
    } catch (err) {
      console.error('Custom difficulty practice generation failed:', err)
      setMode('generation_failed')
    }
  }

  // Intersection Observer — records focusedAt when question card scrolls into view
  useEffect(() => {
    if (questions.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          const idx = Number(entry.target.getAttribute('data-idx'))
          if (entry.isIntersecting && !hasFocused.current[idx]) {
            hasFocused.current[idx] = true
            focusedAt.current[idx] = Date.now()
          }
        })
      },
      { threshold: 0.4 }
    )
    cardRefs.current.forEach(ref => { if (ref) observer.observe(ref) })
    return () => observer.disconnect()
  }, [questions])

  const getTimeTaken = (idx: number): number => {
    const start = focusedAt.current[idx] ?? Date.now()
    return Math.max(1, Math.floor((Date.now() - start) / 1000))
  }

  const handleSelect = useCallback(async (idx: number, opt: string) => {
    // Only allow one answer per question
    if (submitted[idx]) return

    const q = questions[idx]
    const timeTaken = getTimeTaken(idx)

    // Optimistically mark selected + submitted immediately for snappy UX
    setSelected(prev => ({ ...prev, [idx]: opt }))
    setSubmitted(prev => ({ ...prev, [idx]: true }))

    try {
      const res = await api.post('/quiz/attempt', {
        session_id: sessionId,
        question_id: q.question_id,
        node_id: nodeId,
        selected_option: opt,
        time_taken_sec: timeTaken
      })
      setAnswerResults(prev => ({
        ...prev,
        [idx]: { correct: res.data.correct, correct_option: res.data.correct_option }
      }))
    } catch {
      setAnswerResults(prev => ({
        ...prev,
        [idx]: { correct: false, correct_option: '' }
      }))
    }
  }, [questions, submitted, sessionId, nodeId])

  const allAnswered = questions.length > 0 && questions.every((_, i) => submitted[i])

  const handleSubmit = async () => {
    setSubmitting(true)
    const allAnswers = questions.map((q, i) => ({
      ...q,
      selected: selected[i],
      correct: answerResults[i]?.correct ?? false,
      correct_option: answerResults[i]?.correct_option ?? ''
    }))
    const correct = allAnswers.filter(a => a.correct).length
    const score = Math.round((correct / allAnswers.length) * 100)
    const totalTime = Math.floor(
      Object.values(focusedAt.current).reduce((sum, t) => sum + (Date.now() - t), 0) / 1000
    )
    try {
      await api.post('/quiz/submit', {
        session_id: sessionId,
        node_id: nodeId,
        score_pct: score,
        correct_count: correct,
        total_questions: allAnswers.length,
        time_taken_sec: totalTime
      })
    } catch {}
    setResult({ score, correct, total: allAnswers.length, answers: allAnswers })
    setSubmitting(false)
  }

  const handleAbandon = async () => {
    try { await api.post('/quiz/abandon', { session_id: sessionId, node_id: nodeId }) } catch {}
    router.push(`/learn/${nodeId}`)
  }

  // Browser's built-in text-to-speech — free, no new infrastructure,
  // works for real or generated questions alike. Available on every
  // question for anyone, just visually emphasized for Auditory-type
  // students rather than exclusive to them.
  const readAloud = (q: any) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const text = `${q.question_text}. Option A: ${q.option_a}. Option B: ${q.option_b}. Option C: ${q.option_c}. Option D: ${q.option_d}.`
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    window.speechSynthesis.speak(utterance)
    // A student choosing to have a question read aloud is the same
    // kind of behavioral signal as audio_play_count already used for
    // VARK detection — logged now so the data exists; actually adding
    // it as a live classifier feature is a separate, bigger step
    // (touches weekly aggregation + retraining + re-validation).
    tracker.log('read_aloud_click', q.question_id, 0)
  }

  // Auth check only — no auto-fetch anymore, since the student picks
  // a mode first (standard set, or a specific difficulty).
  const [varkLabel, setVarkLabel] = useState<string | null>(null)
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) { router.push('/'); return }
      api.get('/profile/me').then(res => setVarkLabel(res.data.vark_label || res.data.vark_questionnaire_label)).catch(() => {})
    })
  }, [router])

  // ── Choice screen — the "right to ask for a specific difficulty" ──
  if (mode === 'choosing') return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 max-w-lg w-full">
          <h2 className="text-lg font-bold text-[#1E293B] mb-1 text-center">How do you want to practice?</h2>
          <p className="text-sm text-[#64748B] text-center mb-6">Pick a difficulty, or use the standard set.</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <button onClick={() => requestCustomDifficulty('easy')}
              className="p-4 rounded-xl border-2 border-green-200 bg-green-50 hover:border-green-400 transition-all text-left">
              <p className="font-semibold text-green-700">Easy</p>
              <p className="text-xs text-[#64748B] mt-0.5">Build confidence</p>
            </button>
            <button onClick={() => requestCustomDifficulty('just_right')}
              className="p-4 rounded-xl border-2 border-blue-200 bg-blue-50 hover:border-blue-400 transition-all text-left">
              <p className="font-semibold text-blue-700">Just Right</p>
              <p className="text-xs text-[#64748B] mt-0.5">Matched to you</p>
            </button>
            <button onClick={() => requestCustomDifficulty('hard')}
              className="p-4 rounded-xl border-2 border-orange-200 bg-orange-50 hover:border-orange-400 transition-all text-left">
              <p className="font-semibold text-orange-700">Hard</p>
              <p className="text-xs text-[#64748B] mt-0.5">Push yourself</p>
            </button>
            <button onClick={() => requestCustomDifficulty('impossible')}
              className="p-4 rounded-xl border-2 border-red-200 bg-red-50 hover:border-red-400 transition-all text-left">
              <p className="font-semibold text-red-700">Impossible</p>
              <p className="text-xs text-[#64748B] mt-0.5">Real stretch goal</p>
            </button>
          </div>
          <button onClick={loadStandardPractice}
            className="w-full p-3 rounded-xl border border-[#E2E8F0] text-[#475569] font-medium hover:border-[#003087] transition-all text-sm">
            Just give me the standard practice set
          </button>
        </div>
      </main>
    </div>
  )

  // ── Loading ──
  if (mode === 'loading') return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin" />
      </main>
    </div>
  )

  // ── Generation failed ──
  if (mode === 'generation_failed') return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 max-w-sm w-full text-center">
          <div className="w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">⚠️</span>
          </div>
          <h2 className="text-lg font-bold text-[#1E293B] mb-2">Couldn't generate questions</h2>
          <p className="text-sm text-[#64748B] mb-6">Something went wrong. Please try again.</p>
          <button onClick={() => setMode('choosing')}
            className="w-full bg-[#003087] text-white font-semibold py-3 rounded-xl hover:bg-[#0047c8] transition-all">
            Back to Options
          </button>
        </div>
      </main>
    </div>
  )

  // ── Result screen (unchanged) ──
  if (result) return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 max-w-lg w-full text-center">
          <div className={`w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6 ${result.score >= 70 ? 'bg-green-100' : 'bg-orange-100'}`}>
            <span className="text-4xl">{result.score >= 70 ? '🎉' : '📖'}</span>
          </div>
          <h2 className="text-2xl font-bold text-[#1E293B] mb-2">
            {result.score >= 70 ? 'Great work!' : 'Keep practicing!'}
          </h2>
          <p className="text-[#64748B] mb-6">You scored</p>
          <p className={`text-5xl font-bold mb-2 ${result.score >= 70 ? 'text-[#22C55E]' : 'text-[#FF6B00]'}`}>{result.score}%</p>
          <p className="text-[#94A3B8] mb-8">{result.correct} out of {result.total} correct</p>
          <div className="space-y-2 mb-8 text-left">
            {result.answers.map((a: any, i: number) => (
              <div key={i} className={`flex items-center gap-3 p-3 rounded-lg ${a.correct ? 'bg-green-50' : 'bg-red-50'}`}>
                <span>{a.correct ? '✅' : '❌'}</span>
                <p className="text-sm text-[#475569] flex-1 line-clamp-1">{a.question_text}</p>
                {!a.correct && <span className="text-xs text-[#94A3B8]">Ans: {a.correct_option}</span>}
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            <button
              onClick={() => router.push(`/learn/${nodeId}/posttest`)}
              className="w-full bg-[#003087] text-white font-semibold py-3 rounded-xl hover:bg-[#0047c8] transition-all flex items-center justify-center gap-2"
            >
              🎯 Take Post-test
            </button>
            <div className="flex gap-3">
              <button onClick={() => router.push('/learn')}
                className="flex-1 border-2 border-[#E2E8F0] text-[#64748B] font-semibold py-3 rounded-xl hover:border-[#003087] hover:text-[#003087] transition-all">
                Dashboard
              </button>
              <button onClick={() => router.push(`/learn/${nodeId}`)}
                className="flex-1 border-2 border-[#E2E8F0] text-[#64748B] font-semibold py-3 rounded-xl hover:border-[#003087] hover:text-[#003087] transition-all">
                Back to Lesson
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )

  // ── Scrollable quiz ──
  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC]">

        {/* Sticky header */}
        <div className="sticky top-0 z-20 bg-white border-b border-[#E2E8F0] px-8 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="font-bold text-[#1E293B]">Quiz · {nodeId}</h2>
            <span className="text-xs text-[#94A3B8] font-medium">
              {Object.keys(submitted).length} / {questions.length} answered
            </span>
          </div>
          <button onClick={handleAbandon} className="text-xs text-[#94A3B8] hover:text-red-500 transition-colors">
            Exit Quiz
          </button>
        </div>

        {/* Thin overall progress bar under header */}
        <div className="h-1 bg-[#E2E8F0]">
          <div
            className="h-1 bg-[#003087] transition-all duration-300"
            style={{ width: `${(Object.keys(submitted).length / questions.length) * 100}%` }}
          />
        </div>

        {/* Question cards */}
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
          {questions.map((q, idx) => {
            const sel = selected[idx]
            const isSubmitted = submitted[idx]
            const res = answerResults[idx]

            return (
              <div
                key={q.question_id}
                data-idx={idx}
                ref={el => { cardRefs.current[idx] = el }}
                className={`bg-white rounded-2xl border-2 transition-all duration-200 p-6 ${
                  isSubmitted
                    ? res?.correct
                      ? 'border-green-300'
                      : 'border-red-200'
                    : 'border-[#E2E8F0]'
                }`}
              >
                {/* Q number + difficulty + status badge */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#94A3B8] uppercase tracking-wide">
                      Question {idx + 1}
                    </span>
                    {(() => {
                      const badge = getDifficultyBadge(q.relative_difficulty)
                      return (
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badge.className}`}>
                          {badge.label}
                        </span>
                      )
                    })()}
                  </div>
                  {isSubmitted && res && (
                    <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                      res.correct ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'
                    }`}>
                      {res.correct ? '✓ Correct' : '✗ Incorrect'}
                    </span>
                  )}
                </div>

                {/* Image (Visual VARK) */}
                {q.image_url && (
                  <div className="mb-4 rounded-xl overflow-hidden border border-[#E2E8F0] bg-[#F8F9FC]">
                    <img
                      src={q.image_url}
                      alt="Question visual"
                      className="w-full max-h-64 object-contain mx-auto"
                    />
                  </div>
                )}

                {/* Audio (Aural VARK) */}
                {q.question_audio_url && (
                  <div className="mb-4 bg-[#F0F7FF] border border-blue-200 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-base">🎧</span>
                      <p className="text-sm font-semibold text-[#003087]">Listen before answering</p>
                    </div>
                    <audio controls className="w-full" src={q.question_audio_url} />
                  </div>
                )}

                {/* Question text + read-aloud */}
                <div className="flex items-start justify-between gap-3 mb-4">
                  <p className="text-base font-semibold text-[#1E293B] leading-relaxed flex-1">
                    {q.question_text}
                  </p>
                  <button
                    onClick={() => readAloud(q)}
                    title="Read this question aloud"
                    className={`flex-shrink-0 rounded-full transition-all ${
                      varkLabel === 'A'
                        ? 'w-11 h-11 bg-[#003087] text-white hover:bg-[#0047c8] shadow-md text-lg'
                        : 'w-8 h-8 bg-[#F8F9FC] border border-[#E2E8F0] text-[#94A3B8] hover:text-[#003087] hover:border-[#003087] text-sm'
                    } flex items-center justify-center`}
                  >
                    🔊
                  </button>
                </div>

                {/* Visual aid table (V-type) — structured markdown, not
                    an image, so there's no hallucination-accuracy risk */}
                {q.visual_aid_markdown && (
                  <div className="mb-4 bg-[#F8F9FC] border border-[#E2E8F0] rounded-xl p-4 text-sm overflow-x-auto">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        table: ({ ...props }) => <table className="border-collapse w-full" {...props} />,
                        th: ({ ...props }) => <th className="border border-[#E2E8F0] bg-white px-3 py-1.5 text-left font-semibold text-[#1E293B]" {...props} />,
                        td: ({ ...props }) => <td className="border border-[#E2E8F0] px-3 py-1.5 text-[#475569]" {...props} />,
                      }}
                    >
                      {q.visual_aid_markdown}
                    </ReactMarkdown>
                  </div>
                )}

                {/* Options */}
                <div className="space-y-2.5">
                  {['a', 'b', 'c', 'd'].map(opt => {
                    const text = q[`option_${opt}`]
                    if (!text) return null
                    const upper = opt.toUpperCase()
                    const isSelected = sel === upper
                    const isCorrectAnswer = res?.correct_option?.toUpperCase() === upper

                    let optClass = 'border-[#E2E8F0] text-[#475569] hover:border-[#003087]'
                    if (isSubmitted) {
                      if (isCorrectAnswer) {
                        optClass = 'border-green-400 bg-green-50 text-green-800'
                      } else if (isSelected && !res?.correct) {
                        optClass = 'border-red-300 bg-red-50 text-red-700'
                      } else {
                        optClass = 'border-[#E2E8F0] text-[#94A3B8] opacity-60'
                      }
                    } else if (isSelected) {
                      optClass = 'border-[#003087] bg-[#EFF6FF] text-[#003087]'
                    }

                    return (
                      <button
                        key={opt}
                        onClick={() => handleSelect(idx, upper)}
                        disabled={isSubmitted}
                        className={`w-full text-left py-3 px-4 rounded-xl border-2 text-sm font-medium transition-all ${optClass} disabled:cursor-default`}
                      >
                        <span className="font-bold mr-2">{upper}.</span>{text}
                        {isSubmitted && isCorrectAnswer && (
                          <span className="ml-2 text-green-600">✓</span>
                        )}
                        {isSubmitted && isSelected && !res?.correct && isSelected && (
                          <span className="ml-2 text-red-500">✗</span>
                        )}
                      </button>
                    )
                  })}
                </div>

                {/* Explanation after answer (if available) */}
                {isSubmitted && q.explanation && (
                  <div className="mt-4 bg-[#F8F9FC] border border-[#E2E8F0] rounded-xl p-3">
                    <p className="text-xs font-semibold text-[#64748B] mb-1">💡 Explanation</p>
                    <p className="text-sm text-[#475569]">{q.explanation}</p>
                  </div>
                )}
              </div>
            )
          })}

          {/* Submit button — only active when all answered */}
          <div className="pb-8">
            {!allAnswered && (
              <p className="text-center text-sm text-[#94A3B8] mb-3">
                Answer all {questions.length} questions to submit
              </p>
            )}
            <button
              onClick={handleSubmit}
              disabled={!allAnswered || submitting}
              className="w-full bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-4 rounded-xl transition-all text-base"
            >
              {submitting ? 'Submitting...' : allAnswered ? 'Submit Quiz →' : `${questions.length - Object.keys(submitted).length} questions remaining`}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}