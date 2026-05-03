'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AdminExport() {
  const router = useRouter()
  const [loading, setLoading] = useState<string | null>(null)
  const [authed, setAuthed] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) router.push('/')
      else setAuthed(true)
    })
  }, [router])

  const downloadCSV = async (endpoint: string, filename: string) => {
    setLoading(filename)
    try {
      const res = await api.get(endpoint, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      alert('Export failed. Make sure backend is running.')
    }
    setLoading(null)
  }

  const exports = [
    {
      label: 'All Students',
      desc: 'Student profiles, VARK labels, IRT scores, risk scores',
      endpoint: '/admin/export/students',
      filename: 'learn_students.csv',
      icon: '👥',
    },
    {
      label: 'Interaction Logs',
      desc: 'All raw events — scroll, video, audio, quiz events',
      endpoint: '/admin/export/interactions',
      filename: 'learn_interactions.csv',
      icon: '📋',
    },
    {
      label: 'Quiz Results',
      desc: 'All quiz attempts with scores and time taken',
      endpoint: '/admin/export/quiz-results',
      filename: 'learn_quiz_results.csv',
      icon: '📝',
    },
    {
      label: 'Unit Progress',
      desc: 'Per-student progress per node with completion status',
      endpoint: '/admin/export/unit-progress',
      filename: 'learn_unit_progress.csv',
      icon: '📊',
    },
    {
      label: 'Weekly Stats',
      desc: 'Weekly aggregated stats per student',
      endpoint: '/admin/export/weekly-stats',
      filename: 'learn_weekly_stats.csv',
      icon: '📅',
    },
    {
      label: 'Question Attempts',
      desc: 'Individual question-level attempts with correctness',
      endpoint: '/admin/export/question-attempts',
      filename: 'learn_question_attempts.csv',
      icon: '❓',
    },
  ]

  if (!authed) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
    </div>
  )

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/admin" className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Admin</Link>
          <h1 className="text-xl font-bold text-[#1E293B]">Export Research Data</h1>
        </div>

        <div className="bg-[#FFF7ED] border border-orange-200 rounded-xl p-4 mb-6 flex items-start gap-3">
          <span className="text-lg">⚠️</span>
          <div>
            <p className="text-sm font-semibold text-orange-800">Research Data — Handle with Care</p>
            <p className="text-xs text-orange-700 mt-0.5">All exports contain anonymised participant data. Do not share outside the research team.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4">
          {exports.map(exp => (
            <div key={exp.label} className="bg-white rounded-xl border border-[#E2E8F0] p-5 flex items-center gap-4">
              <div className="w-12 h-12 bg-[#F8F9FC] rounded-xl flex items-center justify-center text-2xl flex-shrink-0">
                {exp.icon}
              </div>
              <div className="flex-1">
                <p className="font-semibold text-[#1E293B]">{exp.label}</p>
                <p className="text-sm text-[#64748B]">{exp.desc}</p>
                <p className="text-xs text-[#94A3B8] mt-0.5 font-mono">{exp.filename}</p>
              </div>
              <button
                onClick={() => downloadCSV(exp.endpoint, exp.filename)}
                disabled={loading === exp.filename}
                className="bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition-all flex items-center gap-2 flex-shrink-0"
              >
                {loading === exp.filename ? (
                  <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"/> Exporting...</>
                ) : (
                  <>⬇ Download</>
                )}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}