'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import ContentForm from '@/components/admin/ContentForm'

export default function EditContentPage() {
  const { nodeId } = useParams()
  const router = useRouter()
  const [node, setNode] = useState<any>(null)

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      try { const res = await api.get(`/admin/content/${nodeId}`); setNode(res.data) } catch { router.push('/admin/content') }
    }
    init()
  }, [nodeId, router])

  if (!node) return <div className="min-h-screen flex items-center justify-center"><div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/></div>
  return <ContentForm existing={node} />
}