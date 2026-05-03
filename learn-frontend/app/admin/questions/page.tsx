import { Suspense } from 'react'
import AdminQuestionsContent from './AdminQuestionsContent'

export default function AdminQuestionsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin" /></div>}>
      <AdminQuestionsContent />
    </Suspense>
  )
}