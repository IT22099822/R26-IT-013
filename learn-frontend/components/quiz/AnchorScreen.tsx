'use client'
import { useState, useRef } from 'react'
import api from '@/lib/api'
import Sidebar from '@/components/shared/Sidebar'

interface AnchorScreenProps {
  questions: any[]
  nodeId: string
  testType: 'pre' | 'post'
  sessionId: string
  onComplete: (summary?: any) => void
}

export default function AnchorScreen({ questions, nodeId, testType, sessionId, onComplete }: AnchorScreenProps) {
  const [current, setCurrent] = useState(0)
  const [selected, setSelected] = useState('')
  const [answers, setAnswers] = useState<any[]>([])
  const [startTime, setStartTime] = useState(Date.now())
  const [submitting, setSubmitting] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  const label = testType === 'pre' ? 'Quick Check · Before You Start' : 'Final Check · Post-test'
  const subtitle = testType === 'pre'
    ? "Answer these quick questions before the lesson. No pressure — your answers won't affect your score."
    : "Answer these questions to complete the lesson. No feedback shown."

  const handleSelect = (opt: string) => setSelected(opt)

  const handleNext = async () => {
    if (!selected) return
    const q = questions[current]
    const timeTaken = Math.floor((Date.now() - startTime) / 1000)

    const newAnswers = [...answers, {
      question_id: q.question_id,
      selected_option: selected,
      time_taken_sec: timeTaken
    }]
    setAnswers(newAnswers)
    setSelected('')
    setStartTime(Date.now())

    // reset audio on question change
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }

    if (current < questions.length - 1) {
      setCurrent(current + 1)
    } else {
      setSubmitting(true)
      let summary
      try {
        const res = await api.post('/quiz/anchor-submit', {
          session_id: sessionId,
          node_id: nodeId,
          test_type: testType,
          answers: newAnswers
        })
        summary = res.data
      } catch (e) {
        console.error('Anchor submit failed', e)
      }
      setSubmitting(false)
      onComplete(summary)
    }
  }

  const q = questions[current]

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 min-h-screen bg-[#F8F9FC] flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl border border-[#E2E8F0] p-8 max-w-2xl w-full">

          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${testType === 'pre' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}`}>
                {testType === 'pre' ? '📋 Pre-check' : '🎯 Post-test'}
              </span>
              <span className="text-xs text-[#94A3B8]">{nodeId}</span>
            </div>
            <h2 className="text-lg font-bold text-[#1E293B]">{label}</h2>
            <p className="text-sm text-[#64748B] mt-1">{subtitle}</p>
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 bg-[#E2E8F0] rounded-full h-1.5">
              <div
                className="bg-[#003087] h-1.5 rounded-full transition-all"
                style={{ width: `${(current / questions.length) * 100}%` }}
              />
            </div>
            <span className="text-xs text-[#64748B] font-medium whitespace-nowrap">
              {current + 1} / {questions.length}
            </span>
          </div>

          {/* Image (Visual VARK) */}
          {q.image_url && (
            <div className="mb-5 rounded-xl overflow-hidden border border-[#E2E8F0] bg-[#F8F9FC]">
              <img
                src={q.image_url}
                alt="Question visual"
                className="w-full max-h-64 object-contain mx-auto"
              />
            </div>
          )}

          {/* Audio (Aural VARK) */}
          {q.question_audio_url && (
            <div className="mb-5 bg-[#F0F7FF] border border-blue-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">🎧</span>
                <p className="text-sm font-semibold text-[#003087]">Listen before answering</p>
              </div>
              <audio
                ref={audioRef}
                controls
                className="w-full"
                src={q.question_audio_url}
              />
            </div>
          )}

          {/* Question text */}
          <p className="text-base font-semibold text-[#1E293B] leading-relaxed mb-5">{q.question_text}</p>

          {/* Options */}
          <div className="space-y-3 mb-6">
            {['a', 'b', 'c', 'd'].map(opt => {
              const text = q[`option_${opt}`]
              if (!text) return null
              const upper = opt.toUpperCase()
              return (
                <button
                  key={opt}
                  onClick={() => handleSelect(upper)}
                  className={`w-full text-left py-3.5 px-5 rounded-xl border-2 text-sm font-medium transition-all ${
                    selected === upper
                      ? 'border-[#003087] bg-[#EFF6FF] text-[#003087]'
                      : 'border-[#E2E8F0] text-[#475569] hover:border-[#003087]'
                  }`}
                >
                  <span className="font-bold mr-2">{upper}.</span>{text}
                </button>
              )
            })}
          </div>

          {/* No feedback note */}
          <p className="text-xs text-[#94A3B8] text-center mb-4">
            ℹ️ Answers are not shown for this check — results are recorded for your progress tracking.
          </p>

          {/* Next / Submit */}
          <button
            onClick={handleNext}
            disabled={!selected || submitting}
            className="w-full bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-3.5 rounded-xl transition-all"
          >
            {submitting
              ? 'Saving...'
              : current < questions.length - 1
              ? 'Next →'
              : testType === 'pre' ? 'Start Lesson →' : 'Complete Lesson ✓'}
          </button>
        </div>
      </main>
    </div>
  )
}