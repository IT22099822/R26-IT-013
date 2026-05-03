'use client'
import { useEffect, useState } from 'react'
import api from '@/lib/api'

export default function LearningGuide({ nodeId }: { nodeId: string }) {
  const [message, setMessage] = useState<string | null>(null)
  const [situation, setSituation] = useState<string>('lesson_intro')
  const [open, setOpen] = useState(false)
  const [visible, setVisible] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setMessage(null)
    setOpen(false)
    setVisible(false)
    api.get('/profile/guide-message', { params: { node_id: nodeId } })
      .then(res => {
        if (cancelled) return
        setMessage(res.data.message)
        setSituation(res.data.situation)
        setLoading(false)
        if (res.data.message) {
          setTimeout(() => {
            if (cancelled) return
            setOpen(true)
            setTimeout(() => { if (!cancelled) setVisible(true) }, 20)
          }, 800)
        }
      })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [nodeId])

  const toggleOpen = () => {
    if (open) {
      setVisible(false)
      setTimeout(() => setOpen(false), 200)
    } else {
      setOpen(true)
      setTimeout(() => setVisible(true), 20)
    }
  }

  if (!message && !loading) return null

  return (
    <div className="fixed bottom-6 right-6 z-40">
      {open && message && (
        <div className={`absolute bottom-16 right-0 w-80 bg-white rounded-2xl shadow-2xl border border-[#E2E8F0] p-5 mb-2 transition-all duration-200 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}`}>
          <div className="flex items-start justify-between mb-2">
            <span className="text-xs font-bold text-[#003087] uppercase tracking-wide">
              {situation === 'gap_detected' ? '💡 Worth Knowing' : '🧭 Your Guide'}
            </span>
            <button onClick={toggleOpen} className="text-[#94A3B8] hover:text-[#1E293B] text-sm leading-none">✕</button>
          </div>
          <p className="text-sm text-[#1E293B] leading-relaxed">{message}</p>
        </div>
      )}
      <button
        onClick={toggleOpen}
        disabled={!message}
        className="w-14 h-14 bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#94A3B8] rounded-full shadow-lg flex items-center justify-center text-2xl transition-all hover:scale-105"
        title="Your learning guide"
      >
        🧭
      </button>
    </div>
  )
}