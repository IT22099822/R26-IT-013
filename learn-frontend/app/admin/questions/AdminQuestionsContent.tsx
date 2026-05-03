'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AdminQuestionsContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedNode = searchParams.get('node') || ''

  const [progress, setProgress] = useState<any[]>([])
  const [questions, setQuestions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState<string | null>(null)
  const [adminRole, setAdminRole] = useState<string>('')

  // Delete modal state
  const [deleteTarget, setDeleteTarget] = useState<any | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const loadData = async () => {
    const [progRes, qRes] = await Promise.all([
      api.get('/admin/questions/progress'),
      selectedNode
        ? api.get(`/admin/questions/by-node/${selectedNode}`)
        : api.get('/admin/questions'),
    ])
    setProgress(progRes.data)
    setQuestions(qRes.data)
    setLoading(false)
  }

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try {
        const checkRes = await api.get('/admin/check', {
          headers: { Authorization: `Bearer ${data.session.access_token}` }
        })
        setAdminRole(checkRes.data.role)
      } catch { router.push('/learn'); return }
      await loadData()
    }
    init()
  }, [router, selectedNode])

  const publishQuestion = async (qid: string) => {
    setPublishing(qid)
    try {
      await api.post(`/admin/questions/${qid}/publish`)
      await loadData()
    } catch (e: any) {
      alert('Error: ' + (e.response?.data?.detail || e.message))
    } finally {
      setPublishing(null)
    }
  }

  const publishAll = async () => {
    const drafts = questions.filter(q => q.status === 'draft')
    for (const q of drafts) {
      await api.post(`/admin/questions/${q.question_id}/publish`)
    }
    await loadData()
  }

  const openDeleteModal = (q: any) => {
    setDeleteTarget(q)
    setDeleteConfirmText('')
    setDeleteError('')
  }

  const closeDeleteModal = () => {
    if (deleting) return
    setDeleteTarget(null)
    setDeleteConfirmText('')
    setDeleteError('')
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    if (deleteConfirmText !== deleteTarget.question_id) {
      setDeleteError('Question ID does not match. Type it exactly.')
      return
    }
    setDeleting(true)
    setDeleteError('')
    try {
      await api.delete(`/admin/questions/${deleteTarget.question_id}`)
      setDeleteTarget(null)
      await loadData()
    } catch (e: any) {
      setDeleteError(e.response?.data?.detail || 'Delete failed. Try again.')
    } finally {
      setDeleting(false)
    }
  }

  const isSuperAdmin = adminRole === 'super_admin'

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin" />
    </div>
  )

  const draftCount = questions.filter(q => q.status === 'draft').length

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          {selectedNode
            ? <button onClick={() => router.push('/admin/questions')} className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← All Nodes</button>
            : <Link href="/admin" className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Admin</Link>
          }
          <h1 className="text-xl font-bold text-[#1E293B]">
            {selectedNode ? `Questions — ${selectedNode}` : 'Question Bank'}
          </h1>
          <Link href={`/admin/questions/new${selectedNode ? `?node=${selectedNode}` : ''}`}
            className="ml-auto bg-[#003087] text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-[#0047c8] transition-all">
            + New Question
          </Link>
        </div>

        {/* Progress tracker */}
        {!selectedNode && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden mb-6">
            <div className="px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0]">
              <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wide">Questions per Node</p>
            </div>
            {progress.length === 0 ? (
              <div className="text-center py-10 text-[#94A3B8] text-sm">No question data yet.</div>
            ) : (
              <div className="divide-y divide-[#E2E8F0]">
                {progress.map((node: any) => (
                  <div key={node.node_id} className="px-5 py-4 flex items-center gap-4 hover:bg-[#F8F9FC]">
                    <span className="font-mono text-sm font-bold text-[#003087] w-12">{node.node_id}</span>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-[#1E293B]">{node.skill_name || node.node_id}</span>
                        <span className="text-xs text-[#64748B]">{node.anchor + node.practice + node.post_test} published</span>
                      </div>
                      <div className="flex gap-2">
                        {[
                          { label: 'Anchor', count: node.anchor, target: 3, color: 'bg-blue-500' },
                          { label: 'Practice', count: node.practice, target: 10, color: 'bg-purple-500' },
                          { label: 'Post-test', count: node.post_test, target: 5, color: 'bg-orange-500' },
                        ].map(t => (
                          <div key={t.label} className="flex-1">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-xs text-[#94A3B8]">{t.label}</span>
                              <span className="text-xs text-[#64748B]">{t.count}/{t.target}</span>
                            </div>
                            <div className="w-full bg-[#E2E8F0] rounded-full h-1.5">
                              <div className={`${t.color} h-1.5 rounded-full transition-all`}
                                style={{ width: `${Math.min((t.count / t.target) * 100, 100)}%` }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {node.questions_ready && (
                        <span className="text-xs bg-green-100 text-green-700 font-semibold px-2 py-0.5 rounded-full">✓ Ready</span>
                      )}
                      <button onClick={() => router.push(`/admin/questions?node=${node.node_id}`)}
                        className="text-xs text-[#003087] hover:underline font-medium">
                        View
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Questions list */}
        {(selectedNode || questions.length > 0) && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
            <div className="px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] flex items-center justify-between">
              <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wide">
                {selectedNode ? `Questions in ${selectedNode}` : 'All Questions'} ({questions.length})
              </p>
              {draftCount > 0 && (
                <button onClick={publishAll}
                  className="text-xs bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700 transition-colors font-medium">
                  Publish All Drafts ({draftCount})
                </button>
              )}
            </div>
            {questions.length === 0 ? (
              <div className="text-center py-10 text-[#94A3B8] text-sm">No questions for this node yet.</div>
            ) : (
              <div className="divide-y divide-[#E2E8F0]">
                {questions.map((q: any) => (
                  <div key={q.question_id} className="px-5 py-4 hover:bg-[#F8F9FC]">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-mono text-xs text-[#003087] font-bold">{q.question_id}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            q.status === 'published' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                          }`}>{q.status}</span>
                          <span className="text-xs bg-[#F1F5F9] text-[#64748B] px-2 py-0.5 rounded-full">{q.question_type}</span>
                          {q.vark_type && (
                            <span className="text-xs bg-purple-50 text-purple-600 px-2 py-0.5 rounded-full">{q.vark_type}</span>
                          )}
                          {q.image_url && (
                            <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">🖼️ Image</span>
                          )}
                          {q.question_audio_url && (
                            <span className="text-xs bg-orange-50 text-orange-600 px-2 py-0.5 rounded-full">🎧 Audio</span>
                          )}
                        </div>
                        <p className="text-sm text-[#1E293B]">{q.question_text}</p>
                        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                          {['A','B','C','D'].filter(o => q[`option_${o.toLowerCase()}`]).map(o => (
                            <p key={o} className={`text-xs ${q.correct_option?.toUpperCase() === o ? 'text-green-600 font-semibold' : 'text-[#64748B]'}`}>
                              {o}. {q[`option_${o.toLowerCase()}`]}
                              {q.correct_option?.toUpperCase() === o && ' ✓'}
                            </p>
                          ))}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex flex-col gap-2 shrink-0 items-end">
                        <button
                          onClick={() => router.push(`/admin/questions/${q.question_id}`)}
                          className="text-xs text-[#003087] hover:underline font-medium">
                          Edit
                        </button>
                        {q.status === 'draft' && (
                          <button
                            onClick={() => publishQuestion(q.question_id)}
                            disabled={publishing === q.question_id}
                            className="text-xs bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors">
                            {publishing === q.question_id ? '...' : 'Publish'}
                          </button>
                        )}
                        {(isSuperAdmin || q.status === 'draft') && (
                          <button
                            onClick={() => openDeleteModal(q)}
                            className="text-xs text-red-400 hover:text-red-600 font-medium transition-colors">
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeDeleteModal} />
          <div className="relative bg-white rounded-2xl border border-[#E2E8F0] p-6 w-full max-w-md shadow-xl">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl">🗑️</span>
            </div>
            <h2 className="text-lg font-bold text-[#1E293B] text-center mb-1">Delete Question</h2>
            <p className="text-sm text-[#64748B] text-center mb-5">
              This will permanently delete{' '}
              <span className="font-bold text-[#1E293B]">{deleteTarget.question_id}</span>.
              This cannot be undone.
            </p>

            {deleteTarget.status === 'published' && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-4">
                <p className="text-xs text-red-700 font-medium">
                  ⚠️ This is a <span className="font-bold">published</span> question. Deleting it may affect student data and quiz results.
                </p>
              </div>
            )}

            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Type <span className="font-mono font-bold text-[#1E293B]">{deleteTarget.question_id}</span> to confirm
            </label>
            <input
              type="text"
              value={deleteConfirmText}
              onChange={e => { setDeleteConfirmText(e.target.value); setDeleteError('') }}
              placeholder={deleteTarget.question_id}
              className="w-full border-2 border-[#E2E8F0] rounded-xl px-4 py-2.5 text-sm font-mono focus:border-red-400 focus:outline-none mb-3"
              autoFocus
            />
            {deleteError && <p className="text-xs text-red-600 mb-3">{deleteError}</p>}

            <div className="flex gap-3">
              <button onClick={closeDeleteModal} disabled={deleting}
                className="flex-1 border-2 border-[#E2E8F0] text-[#64748B] font-semibold py-2.5 rounded-xl hover:border-[#003087] hover:text-[#003087] transition-all disabled:opacity-50">
                Cancel
              </button>
              <button onClick={confirmDelete}
                disabled={deleteConfirmText !== deleteTarget.question_id || deleting}
                className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-2.5 rounded-xl transition-all">
                {deleting ? 'Deleting...' : 'Delete Forever'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}