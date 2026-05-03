'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import api from '@/lib/api'

// LEARN Coach: a chat window grounded in the learner's real progress
// (backend: POST /coach/chat). The browser keeps the conversation and sends
// the recent turns each time, so the chat survives a failed save.

type Turn = { role: 'user' | 'assistant'; content: string }
type Facts = {
  lessons_completed: number
  lessons_total: number
  last_week: { sessions: number; quizzes: number }
  weak_skills: { name: string; questions_to_master: number }[]
  active_lesson: { name: string; questions_to_master: number } | null
}
type Action = { label: string; href: string }

const STARTERS = [
  'How am I doing this week?',
  'What should I study next?',
  "I'm finding it hard to keep up",
]

export default function CoachChat({ open, onClose, interventionId }: {
  open: boolean
  onClose: () => void
  interventionId?: string | null
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [facts, setFacts] = useState<Facts | null>(null)
  const [actions, setActions] = useState<Action[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const started = useRef<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const send = async (history: Turn[]) => {
    setSending(true)
    setError(null)
    try {
      const res = await api.post('/coach/chat', { messages: history, intervention_id: interventionId || null })
      setTurns([...history, { role: 'assistant', content: res.data.reply }])
      setFacts(res.data.facts)
      setActions(res.data.actions || [])
    } catch (err: any) {
      setError(err?.response?.data?.detail || "The coach can't reply right now. Please try again.")
      setTurns(history)
    }
    setSending(false)
  }

  // Opening message once per open (and again if opened for a different check-in)
  useEffect(() => {
    const key = interventionId || 'general'
    if (open && started.current !== key) {
      started.current = key
      setTurns([])
      send([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, interventionId])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, sending])

  const submit = (text: string) => {
    const t = text.trim()
    if (!t || sending) return
    setInput('')
    const history: Turn[] = [...turns, { role: 'user', content: t }]
    setTurns(history)
    send(history)
  }

  if (!open) return null
  const next = facts?.weak_skills?.[0] || facts?.active_lesson || null

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-md bg-white shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}
           role="dialog" aria-label="LEARN Coach">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[#E2E8F0] flex items-center gap-3">
          <div className="w-10 h-10 bg-[#003087] rounded-full flex items-center justify-center text-white text-lg">💬</div>
          <div className="flex-1">
            <p className="font-bold text-[#1E293B] text-sm">LEARN Coach</p>
            <p className="text-xs text-[#64748B]">Talks with you about your real progress</p>
          </div>
          <button onClick={onClose} aria-label="Close coach"
                  className="w-8 h-8 rounded-lg text-[#64748B] hover:bg-[#F8F9FC] hover:text-[#1E293B]">✕</button>
        </div>

        {/* Real progress, from the same facts the coach uses */}
        {facts && (
          <div className="px-5 py-3 border-b border-[#E2E8F0] bg-[#F8F9FC] flex flex-wrap gap-2">
            <span className="text-xs font-medium bg-white border border-[#E2E8F0] text-[#1E293B] px-2.5 py-1 rounded-full">
              📚 {facts.lessons_completed} of {facts.lessons_total} lessons
            </span>
            <span className="text-xs font-medium bg-white border border-[#E2E8F0] text-[#1E293B] px-2.5 py-1 rounded-full">
              🗓️ {facts.last_week.sessions} sessions last week
            </span>
            {next && next.questions_to_master > 0 && (
              <span className="text-xs font-medium bg-orange-50 border border-orange-200 text-[#1E293B] px-2.5 py-1 rounded-full">
                🎯 {next.name}: ~{next.questions_to_master} correct answers to master
              </span>
            )}
          </div>
        )}

        {/* Conversation */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {turns.map((t, i) => (
            <div key={i} className={`flex ${t.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${t.role === 'user'
                ? 'bg-[#003087] text-white rounded-br-md'
                : 'bg-[#F1F5F9] text-[#1E293B] rounded-bl-md'}`}>
                {t.role === 'assistant'
                  ? <div className="[&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold"><ReactMarkdown>{t.content}</ReactMarkdown></div>
                  : t.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-[#F1F5F9] rounded-2xl rounded-bl-md px-4 py-3 flex gap-1" aria-label="Coach is typing">
                <span className="w-2 h-2 bg-[#94A3B8] rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-[#94A3B8] rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-[#94A3B8] rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}
          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2 flex items-center justify-between gap-2">
              <span>{error}</span>
              <button className="font-semibold underline" onClick={() => send(turns)}>Retry</button>
            </div>
          )}
          {!sending && actions.length > 0 && turns.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {actions.map(a => (
                <Link key={a.href} href={a.href} onClick={onClose}
                      className="text-xs font-semibold text-[#003087] bg-[#EFF6FF] border border-blue-200 px-3 py-1.5 rounded-full hover:bg-blue-100">
                  {a.label} →
                </Link>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Quick starters, then the input */}
        {turns.filter(t => t.role === 'user').length === 0 && !sending && (
          <div className="px-5 pb-2 flex flex-wrap gap-2">
            {STARTERS.map(s => (
              <button key={s} onClick={() => submit(s)}
                      className="text-xs text-[#475569] border border-[#E2E8F0] px-3 py-1.5 rounded-full hover:bg-[#F8F9FC]">{s}</button>
            ))}
          </div>
        )}
        <form className="p-4 border-t border-[#E2E8F0] flex gap-2" onSubmit={e => { e.preventDefault(); submit(input) }}>
          <input value={input} onChange={e => setInput(e.target.value)} maxLength={1000} disabled={sending}
                 placeholder="Ask about your progress or how to keep going…"
                 className="flex-1 border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087] disabled:bg-[#F8F9FC]" />
          <button type="submit" disabled={sending || !input.trim()}
                  className="bg-[#003087] hover:bg-[#0047c8] disabled:opacity-40 text-white font-semibold px-4 rounded-xl text-sm">Send</button>
        </form>
        <p className="px-4 pb-3 text-[10px] text-[#94A3B8] text-center">AI coach. It can make mistakes; your progress numbers come straight from the platform.</p>
      </div>
    </div>
  )
}
