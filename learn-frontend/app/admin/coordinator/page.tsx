'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

const DECISION_COLORS: Record<string, string> = {
  intervention_triggered: 'bg-indigo-100 text-indigo-700',
  intervention_suppressed_control_group: 'bg-gray-100 text-gray-600',
  suppressed_cooldown: 'bg-blue-100 text-blue-700',
  no_action_below_threshold: 'bg-gray-100 text-gray-500',
}
const DECISION_LABELS: Record<string, string> = {
  intervention_triggered: 'Triggered',
  intervention_suppressed_control_group: 'Suppressed (Control)',
  suppressed_cooldown: 'Suppressed (Cooldown)',
  no_action_below_threshold: 'Below Threshold',
}

export default function AdminCoordinator() {
  const router = useRouter()
  const [tab, setTab] = useState<'decisions' | 'interventions'>('decisions')
  const [decisions, setDecisions] = useState<any[]>([])
  const [interventions, setInterventions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null)
  const [seedEmail, setSeedEmail] = useState('')
  const [seedScenario, setSeedScenario] = useState('pending_intervention')
  const [seedEngagementDip, setSeedEngagementDip] = useState('')
  const [seeding, setSeeding] = useState(false)
  const [seedMessage, setSeedMessage] = useState<string | null>(null)

  const loadData = async () => {
    try {
      const [dec, interv] = await Promise.all([
        api.get('/admin/coordinator-decisions'),
        api.get('/admin/interventions'),
      ])
      setDecisions(dec.data)
      setInterventions(interv.data)
    } catch {}
  }

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) { router.push('/'); return }
      await loadData()
      setLoading(false)
    }
    init()
  }, [router])

  const runPipeline = async () => {
    setTriggering(true)
    setTriggerMessage(null)
    try {
      await api.post('/admin/run-weekly-pipeline')
      setTriggerMessage('Pipeline started — this runs in the background (weekly stats, VARK, dropout scoring, then coordinator decisions). Check your backend terminal for progress, then click "Refresh" below once it looks complete.')
    } catch (err: any) {
      setTriggerMessage(`Failed to start: ${err?.response?.data?.detail || err.message}`)
    }
    setTriggering(false)
  }

  const runRecoveryCheck = async () => {
    setTriggering(true)
    setTriggerMessage(null)
    try {
      await api.post('/admin/run-recovery-check')
      setTriggerMessage('Recovery check started — checking any interventions sent 7+ days ago. Check your backend terminal for progress.')
    } catch (err: any) {
      setTriggerMessage(`Failed to start: ${err?.response?.data?.detail || err.message}`)
    }
    setTriggering(false)
  }

  const seedDemoData = async () => {
    if (!seedEmail.trim()) { setSeedMessage('Enter a student email first.'); return }
    setSeeding(true)
    setSeedMessage(null)
    try {
      const payload: any = { student_email: seedEmail.trim(), scenario: seedScenario }
      if (seedEngagementDip.trim() !== '') {
        payload.engagement_dip_score = parseFloat(seedEngagementDip)
      }
      const res = await api.post('/admin/seed-demo-data', payload)
      setSeedMessage(`Seeded "${seedScenario}" for ${seedEmail}. Refresh below to see it.`)
      await loadData()
    } catch (err: any) {
      setSeedMessage(`Failed: ${err?.response?.data?.detail || err.message}`)
    }
    setSeeding(false)
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
          <h1 className="text-xl font-bold text-[#1E293B]">Coordinator</h1>
          <span className="text-sm text-[#94A3B8]">
            ({tab === 'decisions' ? decisions.length : interventions.length} {tab})
          </span>
        </div>

        <div className="bg-white rounded-xl border border-[#E2E8F0] p-4 mb-4 flex items-center gap-3 flex-wrap">
          <button
            onClick={runPipeline}
            disabled={triggering}
            className="bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#94A3B8] text-white text-sm font-semibold px-4 py-2 rounded-lg transition-all"
          >
            {triggering ? 'Starting...' : 'Run Weekly Pipeline'}
          </button>
          <button
            onClick={runRecoveryCheck}
            disabled={triggering}
            className="bg-white border border-[#E2E8F0] hover:border-[#003087] disabled:opacity-50 text-[#475569] text-sm font-semibold px-4 py-2 rounded-lg transition-all"
          >
            Run Recovery Check
          </button>
          <button
            onClick={loadData}
            className="bg-white border border-[#E2E8F0] hover:border-[#003087] text-[#475569] text-sm font-semibold px-4 py-2 rounded-lg transition-all"
          >
            Refresh
          </button>
          {triggerMessage && (
            <p className="text-xs text-[#64748B] w-full mt-1">{triggerMessage}</p>
          )}
        </div>

        {/* Demo data seeding — guaranteed to work regardless of live LLM
            calls, natural risk thresholds, or random group assignment.
            For demo-day reliability, not for real research data. */}
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4">
          <p className="text-sm font-semibold text-[#1E293B] mb-1">🎬 Seed Demo Data</p>
          <p className="text-xs text-[#64748B] mb-3">Guarantees a specific scenario on a real student account — doesn't depend on live LLM calls or natural risk scores.</p>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="email"
              placeholder="student@email.com"
              value={seedEmail}
              onChange={e => setSeedEmail(e.target.value)}
              className="border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm flex-1 min-w-[200px]"
            />
            <select
              value={seedScenario}
              onChange={e => setSeedScenario(e.target.value)}
              className="border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm"
            >
              <option value="pending_intervention">Pending Intervention (popup will show)</option>
              <option value="recovered_intervention">Recovered Intervention (full cycle)</option>
              <option value="suppressed_control_recovered">Control — Recovered Anyway (real activity seeded)</option>
              <option value="suppressed_control_not_recovered">Control — Did Not Recover</option>
              <option value="below_threshold">Below Risk Threshold</option>
              <option value="suppressed_cooldown">Suppressed (Cooldown Active)</option>
            </select>
            <input
              type="number"
              min="0" max="1" step="0.05"
              placeholder="Dip score (optional)"
              value={seedEngagementDip}
              onChange={e => setSeedEngagementDip(e.target.value)}
              title="Optional — sets engagement_dip_score independent of the scenario above, to show the second admin-page badge"
              className="border border-[#E2E8F0] rounded-lg px-3 py-2 text-sm w-36"
            />
            <button
              onClick={seedDemoData}
              disabled={seeding}
              className="bg-[#FF6B00] hover:bg-orange-600 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-all"
            >
              {seeding ? 'Seeding...' : 'Seed It'}
            </button>
          </div>
          {seedMessage && <p className="text-xs text-[#64748B] mt-2">{seedMessage}</p>}
        </div>

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setTab('decisions')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              tab === 'decisions' ? 'bg-[#003087] text-white' : 'bg-white text-[#64748B] border border-[#E2E8F0]'
            }`}
          >
            Every Decision
          </button>
          <button
            onClick={() => setTab('interventions')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              tab === 'interventions' ? 'bg-[#003087] text-white' : 'bg-white text-[#64748B] border border-[#E2E8F0]'
            }`}
          >
            Triggered Interventions
          </button>
          <Link
            href="/admin/treatment-control"
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-white text-[#64748B] border border-[#E2E8F0] hover:border-[#003087]"
          >
            Treatment vs. Control →
          </Link>
        </div>

        {tab === 'decisions' && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
            <div className="grid grid-cols-6 gap-3 px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase tracking-wide">
              <span>Time</span>
              <span>Student</span>
              <span>Trigger</span>
              <span>Rule</span>
              <span>Decision</span>
              <span>C4 Summary</span>
            </div>
            {decisions.length === 0 ? (
              <div className="text-center py-12 text-[#94A3B8] text-sm">
                No decisions logged yet — the weekly pipeline hasn't run, or no students have a risk score yet.
              </div>
            ) : decisions.map((d: any) => (
              <div key={d.decision_id} className="grid grid-cols-6 gap-3 px-5 py-3 border-b border-[#E2E8F0] hover:bg-[#F8F9FC] items-center text-sm">
                <span className="text-xs text-[#94A3B8]">
                  {d.timestamp ? new Date(d.timestamp).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                </span>
                <span className="font-mono text-xs text-[#64748B]">{d.student_id?.slice(0, 12)}...</span>
                <span className="text-xs text-[#475569]">{d.trigger_event || '—'}</span>
                <span className="text-xs text-[#475569]">{d.rule_fired || '—'}</span>
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit truncate max-w-full ${DECISION_COLORS[d.final_decision] || 'bg-gray-100 text-gray-600'}`}
                  title={d.final_decision || undefined}
                >
                  {DECISION_LABELS[d.final_decision] || d.final_decision || '—'}
                </span>
                <span className="text-xs text-[#64748B] truncate">{d.c4_recommendation || '—'}</span>
              </div>
            ))}
          </div>
        )}

        {tab === 'interventions' && (
          <div className="bg-white rounded-xl border border-[#E2E8F0] overflow-hidden">
            <div className="grid grid-cols-6 gap-3 px-5 py-3 bg-[#F8F9FC] border-b border-[#E2E8F0] text-xs font-semibold text-[#64748B] uppercase tracking-wide">
              <span>Student</span>
              <span>Risk</span>
              <span>Reason</span>
              <span className="col-span-2">Message</span>
              <span>Recovery</span>
            </div>
            {interventions.length === 0 ? (
              <div className="text-center py-12 text-[#94A3B8] text-sm">
                No interventions triggered yet.
              </div>
            ) : interventions.map((iv: any) => (
              <div key={iv.intervention_id}>
                <div
                  className="grid grid-cols-6 gap-3 px-5 py-3 border-b border-[#E2E8F0] hover:bg-[#F8F9FC] items-center text-sm cursor-pointer"
                  onClick={() => setExpandedId(expandedId === iv.intervention_id ? null : iv.intervention_id)}
                >
                  <span className="font-mono text-xs text-[#64748B]">{iv.student_id?.slice(0, 12)}...</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full w-fit bg-red-100 text-red-700">
                    {iv.risk_score != null ? `${(iv.risk_score * 100).toFixed(0)}%` : '—'}
                  </span>
                  <span className="text-xs text-[#475569] truncate">{iv.risk_reason || '—'}</span>
                  <span className="col-span-2 text-xs text-[#64748B] truncate">
                    {iv.message_sent ? iv.message_sent : <span className="italic text-[#94A3B8]">not generated yet</span>}
                  </span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${recoveryBadgeClass(iv)}`}>
                    {!iv.sent_at ? 'not sent' :
                     !iv.recovery_checked ? 'pending (< 7 days)' :
                     `${(iv.recovery_score * 100).toFixed(0)}%`}
                  </span>
                </div>
                {expandedId === iv.intervention_id && iv.message_sent && (
                  <div className="px-5 py-4 bg-[#F8F9FC] border-b border-[#E2E8F0] text-sm text-[#475569]">
                    <p className="font-semibold text-xs text-[#64748B] uppercase tracking-wide mb-2">Full message</p>
                    <p className="whitespace-pre-wrap">{iv.message_sent}</p>
                    {iv.sent_at && (
                      <p className="text-xs text-[#94A3B8] mt-3">
                        Sent {new Date(iv.sent_at).toLocaleString('en-GB')}
                        {iv.recovery_checked && iv.recovery_score != null && (
                          <> · Recovery: {(iv.recovery_score * 100).toFixed(0)}%
                          (login: {iv.login_within_7days ? 'yes' : 'no'},
                          quiz: {iv.quiz_within_7days ? 'yes' : 'no'},
                          unit completed: {iv.unit_within_7days ? 'yes' : 'no'})</>
                        )}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function recoveryBadgeClass(iv: any) {
  if (!iv.sent_at) return 'bg-gray-100 text-gray-500'
  if (!iv.recovery_checked) return 'bg-blue-100 text-blue-700'
  if (iv.recovery_score >= 0.5) return 'bg-green-100 text-green-700'
  return 'bg-yellow-100 text-yellow-700'
}