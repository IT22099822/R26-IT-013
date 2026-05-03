'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AdminDashboard() {
  const router = useRouter()
  const [stats, setStats] = useState({ nodes: 0, questions: 0, students: 0 })
  const [loading, setLoading] = useState(true)

useEffect(() => {
  const init = async () => {
    const { data } = await supabase.auth.getSession()
    if (!data.session) { router.push('/'); return }

    try {
      await api.get('/admin/check')
    } catch {
      router.push('/learn')
      return
    }

    try {
      const [nodes, questions, students] = await Promise.all([
        api.get('/admin/content'),
        api.get('/admin/questions'),
        api.get('/admin/students')
      ])
      setStats({ nodes: nodes.data.length, questions: questions.data.length, students: students.data.length })
    } catch {}
    setLoading(false)
  }
  init()
}, [router])

  const adminLinks = [
    { href: '/admin/content', icon: '📄', label: 'Content Nodes', desc: 'Manage lessons and media', color: 'bg-blue-50 border-blue-200' },
    { href: '/admin/questions', icon: '❓', label: 'Question Bank', desc: 'Manage MCQ questions', color: 'bg-purple-50 border-purple-200' },
    { href: '/admin/students', icon: '👥', label: 'Students', desc: 'View pilot participants', color: 'bg-green-50 border-green-200' },
    { href: '/admin/coordinator', icon: '🧭', label: 'Coordinator', desc: 'Decisions & interventions', color: 'bg-indigo-50 border-indigo-200' },
    { href: '/admin/logs', icon: '📋', label: 'Interaction Logs', desc: 'Raw event data', color: 'bg-orange-50 border-orange-200' },
    { href: '/admin/export', icon: '⬇️', label: 'Export CSV', desc: 'Download research data', color: 'bg-red-50 border-red-200' },
  ]

  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/></div>

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-9 h-9 bg-[#003087] rounded-lg flex items-center justify-center text-white font-bold text-sm">L</div>
          <div>
            <h1 className="text-xl font-bold text-[#003087]">LEARN Admin</h1>
            <p className="text-xs text-[#94A3B8]">Research Platform Dashboard</p>
          </div>
          <button onClick={async () => { await supabase.auth.signOut(); router.push('/') }}
            className="ml-auto text-sm text-[#64748B] hover:text-red-500 font-medium">
            Logout
          </button>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: 'Content Nodes', value: stats.nodes, icon: '📄' },
            { label: 'Questions', value: stats.questions, icon: '❓' },
            { label: 'Students', value: stats.students, icon: '👥' },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-xl border border-[#E2E8F0] p-5">
              <p className="text-2xl mb-2">{s.icon}</p>
              <p className="text-3xl font-bold text-[#003087]">{s.value}</p>
              <p className="text-sm text-[#64748B] mt-1">{s.label}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-4">
          {adminLinks.map(link => (
            <Link key={link.href} href={link.href}>
              <div className={`bg-white rounded-xl border-2 ${link.color} p-5 cursor-pointer hover:shadow-md transition-all`}>
                <p className="text-2xl mb-2">{link.icon}</p>
                <p className="font-bold text-[#1E293B]">{link.label}</p>
                <p className="text-sm text-[#64748B]">{link.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}