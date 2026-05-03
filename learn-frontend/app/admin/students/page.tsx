'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AdminStudents() {
  const router = useRouter()
  const [students, setStudents] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try {
        const res = await api.get('/admin/students')
        setStudents(res.data)
      } catch {}
      setLoading(false)
    }
    init()
  }, [router])

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
          <h1 className="text-xl font-bold text-[#1E293B]">Students</h1>
          <span className="text-sm text-[#94A3B8]">({students.length} enrolled)</span>
        </div>

        <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
          <div className="grid grid-cols-10 gap-3 px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase tracking-wide">
            <span className="col-span-2">Student ID</span>
            <span>L1</span>
            <span>Level</span>
            <span>Stated VARK</span>
            <span>Behavior VARK</span>
            <span>θ Score</span>
            <span>Mastery</span>
            <span>Risk</span>
            <span>Joined</span>
          </div>
          {students.length === 0 ? (
            <div className="text-center py-12 text-[#94A3B8] text-sm">No students enrolled yet.</div>
          ) : students.map((s: any) => {
            const varkBadgeClass = (label: string | null) =>
              label === 'V' ? 'bg-blue-100 text-blue-700' :
              label === 'A' ? 'bg-green-100 text-green-700' :
              label === 'R' ? 'bg-purple-100 text-purple-700' :
              label === 'K' ? 'bg-orange-100 text-orange-700' :
              'bg-gray-100 text-gray-600'
            const mismatch = s.active_vark_label && s.vark_questionnaire_label &&
              s.active_vark_label !== s.vark_questionnaire_label
            const masteryValues: number[] = s.bkt_mastery ? Object.values(s.bkt_mastery) : []
            const avgMastery = masteryValues.length
              ? masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length
              : null
            const gaps: string[] = s.current_gaps || []
            return (
            <div key={s.student_id} className="grid grid-cols-10 gap-3 px-5 py-3.5 border-b border-[#E2E8F0] hover:bg-[#F8F9FC] items-center text-sm">
              <span className="col-span-2 font-mono text-xs text-[#64748B]">{s.student_id.slice(0, 16)}...</span>
              <span className="capitalize text-[#475569]">{s.l1_language || '—'}</span>
              <span className="capitalize text-[#475569]">{s.self_reported_level || '—'}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full w-fit ${varkBadgeClass(s.vark_questionnaire_label)}`}>
                {s.vark_questionnaire_label || '—'}
              </span>
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded-full w-fit ${varkBadgeClass(s.active_vark_label)} ${mismatch ? 'ring-2 ring-amber-400' : ''}`}
                title={mismatch ? 'Differs from stated VARK label' : undefined}
              >
                {s.active_vark_label || 'pending'}
              </span>
              <span className="font-semibold text-[#003087]">{s.irt_theta?.toFixed(2) ?? '0.00'}</span>
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit cursor-help ${
                  avgMastery === null ? 'bg-gray-100 text-gray-500' :
                  gaps.length > 0 ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'
                }`}
                title={gaps.length > 0 ? `Current gaps: ${gaps.join(', ')}` : 'No current gaps'}
              >
                {avgMastery !== null ? `${(avgMastery * 100).toFixed(0)}%` : '—'}
                {gaps.length > 0 ? ` (${gaps.length} gap${gaps.length > 1 ? 's' : ''})` : ''}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${
                !s.dropout_risk_score ? 'bg-gray-100 text-gray-500' :
                s.dropout_risk_score > 0.6 ? 'bg-red-100 text-red-700' :
                s.dropout_risk_score > 0.3 ? 'bg-yellow-100 text-yellow-700' :
                'bg-green-100 text-green-700'
              }`}>
                {s.dropout_risk_score ? `${(s.dropout_risk_score * 100).toFixed(0)}%` : '—'}
                {s.engagement_dip_score > 0.4 && (
                  <span
                    className="ml-1.5 opacity-70 cursor-help"
                    title={`Engagement dip signal: ${(s.engagement_dip_score * 100).toFixed(0)}% — a separate, lighter-weight indicator that next week may look disengaged. This is NOT the dropout risk score above, and never triggers interventions on its own.`}
                  >
                    ⚠︎
                  </span>
                )}
              </span>
              <span className="text-xs text-[#94A3B8]">
                {s.created_at ? new Date(s.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '—'}
              </span>
            </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}