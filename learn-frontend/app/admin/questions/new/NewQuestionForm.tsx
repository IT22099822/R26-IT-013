'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function NewQuestionForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const preselectedNode = searchParams.get('node') || ''

  const [nodes, setNodes] = useState<any[]>([])
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    question_id: '',
    node_id: preselectedNode,
    question_text: '',
    option_a: '',
    option_b: '',
    option_c: '',
    option_d: '',
    correct_option: 'A',
    explanation: '',
    question_type: 'practice',
    difficulty_tag: '',
    vark_type: '',
    image_url: '',
    question_audio_url: '',
  })

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try { await api.get('/admin/check') } catch { router.push('/learn'); return }
      const res = await api.get('/admin/content')
      setNodes(res.data)
    }
    init()
  }, [router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/admin/questions', {
        ...form,
        difficulty_tag: form.difficulty_tag ? parseFloat(form.difficulty_tag) : null,
        option_c: form.option_c || null,
        option_d: form.option_d || null,
        explanation: form.explanation || null,
        vark_type: form.vark_type || null,
        image_url: form.image_url || null,
        question_audio_url: form.question_audio_url || null,
      })
      router.push(`/admin/questions?node=${form.node_id}`)
    } catch (err: any) {
      alert('Error: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const showImageField = form.vark_type === 'V'
  const showAudioField = form.vark_type === 'A'

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-sm text-[#64748B] hover:text-[#003087]">← Questions</button>
          <h1 className="text-xl font-bold text-[#003087]">New Question</h1>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-[#E2E8F0] p-6 space-y-4">

          {/* Question ID + Node */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">Question ID *</label>
              <input required
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.question_id} onChange={e => set('question_id', e.target.value)} placeholder="e.g. F01_A01" />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">Content Node *</label>
              <select required
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.node_id} onChange={e => set('node_id', e.target.value)}>
                <option value="">Select node...</option>
                {nodes.map(n => <option key={n.node_id} value={n.node_id}>{n.node_id} — {n.skill_name}</option>)}
              </select>
            </div>
          </div>

          {/* Question Text */}
          <div>
            <label className="block text-sm font-medium text-[#1E293B] mb-1">Question Text *</label>
            <textarea required rows={3}
              className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
              value={form.question_text} onChange={e => set('question_text', e.target.value)} />
          </div>

          {/* Options */}
          <div className="grid grid-cols-2 gap-4">
            {['a', 'b', 'c', 'd'].map(opt => (
              <div key={opt}>
                <label className="block text-sm font-medium text-[#1E293B] mb-1">
                  Option {opt.toUpperCase()} {opt === 'a' || opt === 'b' ? '*' : '(optional)'}
                </label>
                <input required={opt === 'a' || opt === 'b'}
                  className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                  value={(form as any)[`option_${opt}`]} onChange={e => set(`option_${opt}`, e.target.value)} />
              </div>
            ))}
          </div>

          {/* Correct + Type + VARK */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">Correct Option *</label>
              <select required
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.correct_option} onChange={e => set('correct_option', e.target.value)}>
                {['A','B','C','D'].map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">Question Type *</label>
              <select required
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.question_type} onChange={e => set('question_type', e.target.value)}>
                <option value="anchor">Anchor (Pre-test)</option>
                <option value="practice">Practice</option>
                <option value="post_test">Post Test</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">VARK Type</label>
              <select
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.vark_type} onChange={e => set('vark_type', e.target.value)}>
                <option value="">None</option>
                <option value="V">V — Visual</option>
                <option value="A">A — Aural</option>
                <option value="R">R — Read/Write</option>
                <option value="K">K — Kinesthetic</option>
              </select>
            </div>
          </div>

          {/* Image URL — only shown when VARK = V */}
          {showImageField && (
            <div className="space-y-2">
              <label className="block text-sm font-medium text-[#1E293B] mb-1">
                🖼️ Image URL <span className="text-[#94A3B8] font-normal">(paste Supabase Storage public URL)</span>
              </label>
              <input
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                placeholder="https://...supabase.co/storage/v1/object/public/..."
                value={form.image_url} onChange={e => set('image_url', e.target.value)} />
              {form.image_url && (
                <div className="rounded-lg border border-[#E2E8F0] overflow-hidden bg-[#F8F9FC] p-2">
                  <p className="text-xs text-[#94A3B8] mb-1">Preview:</p>
                  <img
                    src={form.image_url}
                    alt="Question image preview"
                    className="max-h-40 object-contain rounded"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Audio URL — only shown when VARK = A */}
          {showAudioField && (
            <div className="space-y-2">
              <label className="block text-sm font-medium text-[#1E293B] mb-1">
                🎧 Question Audio URL <span className="text-[#94A3B8] font-normal">(paste Supabase Storage public URL)</span>
              </label>
              <input
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                placeholder="https://...supabase.co/storage/v1/object/public/..."
                value={form.question_audio_url} onChange={e => set('question_audio_url', e.target.value)} />
              {form.question_audio_url && (
                <div className="rounded-lg border border-[#E2E8F0] bg-[#F8F9FC] p-3">
                  <p className="text-xs text-[#94A3B8] mb-2">Preview:</p>
                  <audio controls className="w-full">
                    <source src={form.question_audio_url} type="audio/mpeg" />
                  </audio>
                </div>
              )}
            </div>
          )}

          {/* Difficulty + Explanation */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">
                Difficulty Tag (−4 to +4)
                <span className="text-[#94A3B8] font-normal ml-1">easy = −1.5, medium = 0, hard = +1.5</span>
              </label>
              <input type="number" step="0.1" min="-4" max="4"
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.difficulty_tag} onChange={e => set('difficulty_tag', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#1E293B] mb-1">Explanation</label>
              <input
                className="w-full border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#003087]"
                value={form.explanation} onChange={e => set('explanation', e.target.value)} />
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={saving}
              className="bg-[#003087] text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#002070] disabled:opacity-50 transition-colors">
              {saving ? 'Saving...' : 'Create Question'}
            </button>
            <button type="button" onClick={() => router.back()}
              className="border border-[#E2E8F0] text-[#64748B] px-5 py-2 rounded-lg text-sm font-medium hover:bg-[#F8F9FC] transition-colors">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}