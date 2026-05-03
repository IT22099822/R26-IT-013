'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

export default function AuthCallback() {
  const router = useRouter()

  useEffect(() => {
    const handle = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }

      try {
        // Check if admin first
        const adminCheck = await api.get('/admin/check').catch(() => null)
        if (adminCheck?.data?.is_admin) {
          router.push('/admin')
          return
        }
      } catch {}

      try {
        const res = await api.post('/auth/google', {
          access_token: data.session.access_token
        })
        localStorage.setItem('session_id', res.data.session_id)

        if (!res.data.onboarding_complete) {
          router.push(`/onboarding?step=${res.data.onboarding_step}`)
        } else {
          router.push('/learn')
        }
      } catch {
        router.push('/')
      }
    }
    handle()
  }, [router])

  return (
    <div className="min-h-screen bg-[#F8F9FC] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-[#003087] border-t-transparent rounded-full animate-spin mx-auto mb-4"/>
        <p className="text-[#64748B] font-medium">Signing you in...</p>
      </div>
    </div>
  )
}