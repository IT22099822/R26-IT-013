'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import Link from 'next/link'

export default function TreatmentControlPage() {
  const router = useRouter()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const init = async () => {
      const { data: session } = await supabase.auth.getSession()
      if (!session.session) { router.push('/'); return }
      try {
        const res = await api.get('/admin/treatment-control-comparison')
        setData(res.data)
      } catch (err) {
        console.error('Failed to load comparison:', err)
      }
      setLoading(false)
    }
    init()
  }, [router])

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/>
    </div>
  )

  const Bar = ({ label, treatment, control }: { label: string, treatment: number, control: number }) => (
    <div className="mb-4">
      <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wide mb-1">{label}</p>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs w-16 text-[#475569]">Treatment</span>
        <div className="flex-1 bg-[#E2E8F0] rounded-full h-3">
          <div className="bg-[#003087] h-3 rounded-full" style={{ width: `${treatment * 100}%` }}/>
        </div>
        <span className="text-xs font-semibold text-[#003087] w-12">{(treatment * 100).toFixed(0)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs w-16 text-[#475569]">Control</span>
        <div className="flex-1 bg-[#E2E8F0] rounded-full h-3">
          <div className="bg-gray-400 h-3 rounded-full" style={{ width: `${control * 100}%` }}/>
        </div>
        <span className="text-xs font-semibold text-gray-500 w-12">{(control * 100).toFixed(0)}%</span>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-[#F8F9FC] p-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-2">
          <Link href="/admin" className="text-[#64748B] hover:text-[#003087] text-sm font-medium">← Admin</Link>
          <h1 className="text-xl font-bold text-[#1E293B]">Treatment vs. Control Outcomes</h1>
        </div>
        <p className="text-sm text-[#64748B] mb-6">
          Does the intervention actually help, or would these students have come back anyway?
          Named directly in the C4 spec as the PP2 research finding.
        </p>

        {(!data?.treatment?.n || !data?.control?.n) ? (
          <div className="bg-white rounded-xl border border-[#E2E8F0] p-8 text-center text-[#94A3B8] text-sm">
            Not enough recovery-checked data yet in either group to compare.
            Treatment: {data?.treatment?.n || 0} students. Control: {data?.control?.n || 0} students.
          </div>
        ) : (
          <>
            <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 mb-4">
              <div className="flex justify-between mb-4">
                <span className="text-sm text-[#64748B]">Treatment group (n={data.treatment.n})</span>
                <span className="text-sm text-[#64748B]">Control group (n={data.control.n})</span>
              </div>
              <Bar label="Logged in within 7 days" treatment={data.treatment.login_rate} control={data.control.login_rate} />
              <Bar label="Took a quiz within 7 days" treatment={data.treatment.quiz_rate} control={data.control.quiz_rate} />
              <Bar label="Completed a unit within 7 days" treatment={data.treatment.unit_rate} control={data.control.unit_rate} />
              <div className="mt-6 pt-4 border-t border-[#E2E8F0] flex justify-between items-center">
                <span className="text-sm font-semibold text-[#1E293B]">Average recovery score</span>
                <span className="text-sm">
                  <span className="font-bold text-[#003087]">{data.treatment.avg_recovery_score}</span>
                  {' vs. '}
                  <span className="font-bold text-gray-500">{data.control.avg_recovery_score}</span>
                </span>
              </div>
            </div>

            {data.statistical_test && (
              <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 mb-4">
                <p className="text-sm font-semibold text-[#1E293B] mb-2">Statistical Test</p>
                <p className="text-xs text-[#64748B] mb-3">{data.statistical_test.test}</p>
                <div className="flex gap-6 text-sm">
                  <div>
                    <p className="text-xs text-[#94A3B8]">p-value</p>
                    <p className="font-bold text-[#1E293B]">{data.statistical_test.p_value}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#94A3B8]">Odds ratio</p>
                    <p className="font-bold text-[#1E293B]">{data.statistical_test.odds_ratio ?? 'undefined (zero cell)'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#94A3B8]">Significant at 0.05?</p>
                    <p className={`font-bold ${data.statistical_test.is_significant ? 'text-green-600' : 'text-gray-500'}`}>
                      {data.statistical_test.is_significant ? 'Yes' : 'No'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 text-sm text-[#92400E]">
              {data.honest_note}
              {data.skipped_control_too_recent > 0 && (
                <p className="mt-1 text-xs">
                  ({data.skipped_control_too_recent} additional control-group students haven't reached
                  their 7-day window yet and will be included once they do.)
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}