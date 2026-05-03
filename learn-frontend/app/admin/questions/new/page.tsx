import { Suspense } from 'react'
import NewQuestionForm from './NewQuestionForm'

export default function NewQuestionPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#F8F9FC] p-8 text-[#64748B]">Loading...</div>}>
      <NewQuestionForm />
    </Suspense>
  )
}