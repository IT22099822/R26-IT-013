'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AdminContent() {
  const router = useRouter()
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState<string | null>(null)
  const [togglingQuiz, setTogglingQuiz] = useState<string | null>(null)
  const [adminRole, setAdminRole] = useState<string>('')
  // ── Delete modal state ──
  const [deleteTarget, setDeleteTarget] = useState<any | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const loadNodes = async () => {
    const res = await api.get('/admin/content')
    setNodes(res.data)
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
        await loadNodes()
      } catch {}
      setLoading(false)
    }
    init()
  }, [router])

  const publishNode = async (nodeId: string) => {
    setPublishing(nodeId)
    try {
      await api.post(`/admin/content/${nodeId}/publish`)
      await loadNodes()
    } catch (e: any) {
      alert('Error: ' + (e.response?.data?.detail || e.message))
    } finally {
      setPublishing(null)
    }
  }

  const toggleQuiz = async (nodeId: string) => {
    setTogglingQuiz(nodeId)
    try {
      await api.post(`/admin/content/${nodeId}/toggle-quiz`)
      await loadNodes()
    } catch (e: any) {
      alert('Error: ' + (e.response?.data?.detail || e.message))
    } finally {
      setTogglingQuiz(null)
    }
  }

  const openDeleteModal = (node: any) => {
    setDeleteTarget(node)
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
    if (deleteConfirmText !== deleteTarget.node_id) {
      setDeleteError('Node ID does not match. Please type it exactly.')
      return
    }
    setDeleting(true)
    setDeleteError('')
    try {
      await api.delete(`/admin/content/${deleteTarget.node_id}`)
      setDeleteTarget(null)
      await loadNodes()
    } catch (e: any) {
      setDeleteError(e.response?.data?.detail || 'Delete failed. Try again.')
    } finally {
      setDeleting(false)
    }
  }

  // ── FIXED: was 'superadmin', your DB value is 'super_admin' ──
  const isSuperAdmin = adminRole === 'super_admin'

  const LEVEL_COLORS: Record<number, string> = {
    1: 'bg-blue-100 text-blue-700', 2: 'bg-green-100 text-green-700',
    3: 'bg-orange-100 text-orange-700', 4: 'bg-red-100 text-red-700'
  }
  const STATUS_COLORS: Record<string, string> = {
    draft: 'bg-yellow-100 text-yellow-700',
    published: 'bg-green-100 text-green-700',
    archived: 'bg-gray-100 text-gray-600'
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
    </div>
  )

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/admin" className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Admin</Link>
          <h1 className="text-xl font-bold text-[#1E293B]">Content Nodes</h1>
          <Link href="/admin/content/new"
            className="ml-auto bg-[#003087] text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-[#0047c8] transition-all">
            + New Node
          </Link>
        </div>

        <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
          <div className="grid grid-cols-9 gap-3 px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase tracking-wide">
            <span>Node ID</span>
            <span className="col-span-2">Skill Name</span>
            <span>Level</span>
            <span>CEFR</span>
            <span>Media</span>
            <span>Status</span>
            <span>Quiz</span>
            <span>Actions</span>
          </div>

          {nodes.length === 0 ? (
            <div className="text-center py-12 text-[#94A3B8]">No nodes yet. Create your first content node.</div>
          ) : nodes.map(node => (
            <div key={node.node_id}
              className="grid grid-cols-9 gap-3 px-5 py-3.5 border-b border-[#E2E8F0] hover:bg-[#F8F9FC] items-center">
              <span className="font-mono text-sm font-bold text-[#003087]">{node.node_id}</span>
              <span className="col-span-2 text-sm text-[#1E293B] font-medium">{node.skill_name}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full w-fit ${LEVEL_COLORS[node.level]}`}>
                L{node.level}
              </span>
              <span className="text-xs text-[#64748B]">{node.cefr_level}</span>
              <span className="text-sm">
                {node.has_video ? '🎬' : ''}{node.has_audio ? '🎧' : ''}
                {!node.has_video && !node.has_audio ? '📄' : ''}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${STATUS_COLORS[node.status]}`}>
                {node.status}
              </span>

              <div>
                {node.status === 'published' ? (
                  <button
                    onClick={() => toggleQuiz(node.node_id)}
                    disabled={togglingQuiz === node.node_id}
                    className={`text-xs px-2 py-0.5 rounded-lg font-medium transition-colors disabled:opacity-50 ${
                      node.questions_ready
                        ? 'bg-green-100 text-green-700 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}>
                    {togglingQuiz === node.node_id ? '...' : node.questions_ready ? '✓ Quiz ON' : 'Quiz OFF'}
                  </button>
                ) : (
                  <span className="text-xs text-[#CBD5E1]">—</span>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                <Link href={`/admin/content/${node.node_id}`}
                  className="text-xs text-[#003087] hover:underline font-medium">
                  Edit
                </Link>
                {node.status === 'draft' && (
                  <button
                    onClick={() => publishNode(node.node_id)}
                    disabled={publishing === node.node_id}
                    className="text-xs bg-green-600 text-white px-2 py-0.5 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors font-medium">
                    {publishing === node.node_id ? '...' : 'Publish'}
                  </button>
                )}
                {/* super_admin: delete any node. others: only draft */}
                {(isSuperAdmin || node.status === 'draft') && (
                  <button
                    onClick={() => openDeleteModal(node)}
                    className="text-xs text-red-400 hover:text-red-600 font-medium transition-colors">
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Delete Confirmation Modal ── */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeDeleteModal}/>

          <div className="relative bg-white rounded-2xl border border-[#E2E8F0] p-6 w-full max-w-md shadow-xl">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl">🗑️</span>
            </div>

            <h2 className="text-lg font-bold text-[#1E293B] text-center mb-1">Delete Node</h2>
            <p className="text-sm text-[#64748B] text-center mb-5">
              This will permanently delete{' '}
              <span className="font-bold text-[#1E293B]">{deleteTarget.node_id}</span>{' '}
              and <span className="font-bold text-red-500">all its questions</span>. This cannot be undone.
            </p>

            <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-5">
              <p className="text-xs text-red-700 font-medium">
                ⚠️ Deleting will permanently remove <span className="font-bold">{deleteTarget.node_id}</span>,
                all its questions{deleteTarget.status === 'published' ? ', and any associated student progress data' : ''}.
                This cannot be undone.
              </p>
            </div>

            <label className="block text-xs font-semibold text-[#475569] mb-1.5">
              Type <span className="font-mono font-bold text-[#1E293B]">{deleteTarget.node_id}</span> to confirm
            </label>
            <input
              type="text"
              value={deleteConfirmText}
              onChange={e => { setDeleteConfirmText(e.target.value); setDeleteError('') }}
              placeholder={deleteTarget.node_id}
              className="w-full border-2 border-[#E2E8F0] rounded-xl px-4 py-2.5 text-sm font-mono focus:border-red-400 focus:outline-none mb-3"
              autoFocus
            />

            {deleteError && (
              <p className="text-xs text-red-600 mb-3">{deleteError}</p>
            )}

            <div className="flex gap-3">
              <button
                onClick={closeDeleteModal}
                disabled={deleting}
                className="flex-1 border-2 border-[#E2E8F0] text-[#64748B] font-semibold py-2.5 rounded-xl hover:border-[#003087] hover:text-[#003087] transition-all disabled:opacity-50">
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteConfirmText !== deleteTarget.node_id || deleting}
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