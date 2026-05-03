'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function ContentForm({ existing }: { existing?: any }) {
  const router = useRouter()
  const [form, setForm] = useState({
    node_id: existing?.node_id || '',
    level: existing?.level || 1,
    skill_name: existing?.skill_name || '',
    cefr_level: existing?.cefr_level || 'A1',
    prerequisites: existing?.prerequisites?.join(',') || '',
    summary: existing?.summary || '',
    learning_objectives: existing?.learning_objectives?.join('\n') || '',
    lesson_markdown: existing?.lesson_markdown || '',
    video_youtube_id: existing?.video_youtube_id || '',
    audio_file_url: existing?.audio_file_url || '',
    estimated_minutes: existing?.estimated_minutes || '',
    display_order: existing?.display_order || '',
  })
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [preview, setPreview] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        level: Number(form.level),
        estimated_minutes: form.estimated_minutes ? Number(form.estimated_minutes) : null,
        display_order: Number(form.display_order),
        prerequisites: form.prerequisites ? form.prerequisites.split(',').map((s: string) => s.trim()) : [],
        learning_objectives: form.learning_objectives ? form.learning_objectives.split('\n').filter(Boolean) : [],
      }
      if (existing) {
        await api.put(`/admin/content/${existing.node_id}`, payload)
      } else {
        await api.post('/admin/content', payload)
      }
      router.push('/admin/content')
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Save failed')
    }
    setSaving(false)
  }

  const handlePublish = async () => {
    if (!existing) return
    setPublishing(true)
    try {
      await api.post(`/admin/content/${existing.node_id}/publish`)
      router.push('/admin/content')
    } catch {}
    setPublishing(false)
  }

  const set = (key: string, val: any) => setForm(f => ({ ...f, [key]: val }))

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={() => router.push('/admin/content')} className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Content</button>
          <h1 className="text-xl font-bold text-[#1E293B]">{existing ? `Edit ${existing.node_id}` : 'New Content Node'}</h1>
          <div className="ml-auto flex gap-2">
            <button onClick={() => setPreview(p => !p)} className="border border-[#E2E8F0] text-[#64748B] text-sm font-semibold px-4 py-2 rounded-xl hover:border-[#003087]">
              {preview ? 'Edit' : 'Preview'}
            </button>
            {existing && existing.status !== 'published' && (
              <button onClick={handlePublish} disabled={publishing} className="bg-[#22C55E] text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-green-600 disabled:opacity-50">
                {publishing ? 'Publishing...' : 'Publish'}
              </button>
            )}
            <button onClick={handleSave} disabled={saving} className="bg-[#003087] text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-[#0047c8] disabled:opacity-50">
              {saving ? 'Saving...' : 'Save Draft'}
            </button>
          </div>
        </div>

        {preview ? (
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-8">
            <h2 className="text-2xl font-bold mb-2">{form.skill_name}</h2>
            <p className="text-[#64748B] mb-4">{form.summary}</p>
            {form.learning_objectives && (
              <div className="bg-[#EFF6FF] rounded-xl p-4 mb-4">
                <p className="font-semibold text-[#003087] mb-2">🎯 Learning Objectives</p>
                <ul className="space-y-1">{form.learning_objectives.split('\n').filter(Boolean).map((o: string, i: number) => <li key={i} className="text-sm text-[#475569]">✦ {o}</li>)}</ul>
              </div>
            )}
            {/* ✅ FIXED: use ReactMarkdown instead of dangerouslySetInnerHTML */}
            <div className="prose max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {form.lesson_markdown}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
              <h2 className="font-semibold text-[#1E293B] mb-4">Basic Info</h2>
              <div className="grid grid-cols-2 gap-4">
                {[
                  { key: 'node_id', label: 'Node ID', placeholder: 'e.g. F01', disabled: !!existing },
                  { key: 'skill_name', label: 'Skill Name', placeholder: 'e.g. Simple Present Tense' },
                  { key: 'display_order', label: 'Display Order', placeholder: '1', type: 'number' },
                  { key: 'estimated_minutes', label: 'Estimated Minutes', placeholder: '15', type: 'number' },
                ].map(f => (
                  <div key={f.key}>
                    <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">{f.label}</label>
                    <input type={f.type || 'text'} disabled={f.disabled}
                      value={form[f.key as keyof typeof form]} onChange={e => set(f.key, e.target.value)}
                      placeholder={f.placeholder}
                      className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087] disabled:bg-[#F8F9FC]"/>
                  </div>
                ))}
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">Level</label>
                  <select value={form.level} onChange={e => set('level', e.target.value)}
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087]">
                    {[1,2,3,4].map(l => <option key={l} value={l}>Level {l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">CEFR Level</label>
                  <select value={form.cefr_level} onChange={e => set('cefr_level', e.target.value)}
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087]">
                    {['A1','A2','B1','B2'].map(l => <option key={l}>{l}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">Prerequisites (comma separated node IDs)</label>
                  <input value={form.prerequisites} onChange={e => set('prerequisites', e.target.value)}
                    placeholder="e.g. F01, F02"
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087]"/>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
              <h2 className="font-semibold text-[#1E293B] mb-4">Content</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">Summary</label>
                  <textarea value={form.summary} onChange={e => set('summary', e.target.value)} rows={2}
                    placeholder="Brief description of this lesson..."
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087] resize-none"/>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">Learning Objectives (one per line)</label>
                  <textarea value={form.learning_objectives} onChange={e => set('learning_objectives', e.target.value)} rows={4}
                    placeholder="Understand when to use simple present&#10;Form positive and negative sentences&#10;Ask questions in simple present"
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087] resize-none"/>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">Lesson Content (Markdown supported)</label>
                  <textarea value={form.lesson_markdown} onChange={e => set('lesson_markdown', e.target.value)} rows={16}
                    placeholder="## Introduction&#10;&#10;Write your lesson content here using **Markdown**..."
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087] font-mono resize-y"/>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-[#E2E8F0] p-6">
              <h2 className="font-semibold text-[#1E293B] mb-4">Media</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] mb-1.5">YouTube Video ID</label>
                  <input value={form.video_youtube_id} onChange={e => set('video_youtube_id', e.target.value)}
                    placeholder="e.g. dQw4w9WgXcQ"
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087]"/>
                  <p className="text-xs text-[#94A3B8] mt-1">The ID from youtube.com/watch?v=<strong>THIS_PART</strong></p>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-[#1E293B] border border-[#E2E8F0] mb-1.5">Audio File URL</label>
                  <input value={form.audio_file_url} onChange={e => set('audio_file_url', e.target.value)}
                    placeholder="https://..."
                    className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#003087]"/>
                  <p className="text-xs text-[#94A3B8] mt-1">Direct link to .mp3 or .wav file</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}