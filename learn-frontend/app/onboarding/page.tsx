'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import api from '@/lib/api'

const VARK_QUESTIONS = [
  { q: "You are helping someone who wants to go to your town centre. You would:", options: { V: "Draw a map", A: "Tell them the directions", R: "Write down the directions", K: "Walk with them" } },
  { q: "You are not sure whether a word should be spelled 'dependent' or 'dependant'. You would:", options: { V: "See the words in your mind and choose by how they look", A: "Think about how each word sounds", R: "Look it up in the dictionary", K: "Write both words on paper and choose one" } },
  { q: "You are planning a holiday for a group. You want feedback on the plan. You would:", options: { V: "Use a map or website to show them", A: "Phone, text or email them", R: "Give them a copy of the printed itinerary", K: "Describe some of the highlights" } },
  { q: "You are going to cook something as a treat. You would:", options: { V: "Look through a cookbook for ideas", A: "Ask friends for suggestions", R: "Use a recipe you know works", K: "Cook something you've made before" } },
  { q: "A group of tourists wants to learn about the history of your town. You would:", options: { V: "Show them a map of the town", A: "Talk about the history", R: "Give them a book about the town", K: "Take them on a walking tour" } },
  { q: "You prefer a teacher or presenter who uses:", options: { V: "Diagrams, charts and graphs", A: "Question and answer sessions", R: "Handouts and readings", K: "Demonstrations and examples" } },
  { q: "You have finished a competition and want to tell others about it. You would:", options: { V: "Show them photos or video", A: "Phone a friend and tell them", R: "Write about it on social media", K: "Demonstrate what you did" } },
  { q: "You want to learn a new program or app. You would:", options: { V: "Watch a video tutorial", A: "Ask someone to walk you through it", R: "Read the instruction manual", K: "Just start using it and figure it out" } },
  { q: "You enjoy learning about something when:", options: { V: "There are pictures, videos or maps to look at", A: "You can listen to someone explain it", R: "There is a lot of reading material", K: "There is something practical you can do" } },
  { q: "You have a problem with your knee. You would prefer the doctor:", options: { V: "Show you a diagram of the injury", A: "Explain what is wrong", R: "Give you a pamphlet about the problem", K: "Show you what is wrong using a model" } },
  { q: "When you study, you prefer:", options: { V: "Diagrams and visuals", A: "Talking through ideas", R: "Notes and written summaries", K: "Practical application" } },
  { q: "You like websites that have:", options: { V: "Interesting design and visuals", A: "Audio explanations and podcasts", R: "Lots of written content", K: "Interactive features" } },
  { q: "You remember things best when:", options: { V: "You can picture them visually", A: "You hear them out loud", R: "You write them down", K: "You physically do them" } },
  { q: "When choosing a course, you look at:", options: { V: "The course visuals and layout", A: "Talking to others about it", R: "Reading the course description", K: "Trying a sample lesson" } },
  { q: "You want to find out about a new product. You prefer to:", options: { V: "Look at images and videos", A: "Hear a review from someone", R: "Read the product description", K: "Try it out" } },
  { q: "When explaining something to someone, you tend to:", options: { V: "Draw a diagram or show images", A: "Explain verbally step by step", R: "Write out an explanation", K: "Show them physically how to do it" } },
]

function OnboardingContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [step, setStep] = useState(searchParams.get('step') || 'consent')
  const [loading, setLoading] = useState(false)
  const [consent1, setConsent1] = useState(false)
  const [consent2, setConsent2] = useState(false)
  const [profile, setProfile] = useState({ l1_language: '', english_medium: null as boolean | null, self_reported_level: '' })
  const [varkIndex, setVarkIndex] = useState(0)
  const [varkAnswers, setVarkAnswers] = useState<Record<number, string>>({})
  const [diagIndex, setDiagIndex] = useState(0)
  const [diagQuestions, setDiagQuestions] = useState<any[]>([])
  const [diagAnswers, setDiagAnswers] = useState<any[]>([])
  const [diagTimer, setDiagTimer] = useState(30)
  const [selectedOption, setSelectedOption] = useState('')

  useEffect(() => {
    if (step === 'diagnostic') {
      api.get('/content/nodes').then(() => {})
      api.get('/onboarding/status').then(r => {
        if (r.data.onboarding_step === 'diagnostic') loadDiagnostic()
      }).catch(() => loadDiagnostic())
    }
  }, [step])

  const loadDiagnostic = async () => {
    try {
      // Fetch anchor questions via admin bypass or public endpoint
      const res = await api.get('/admin/questions')
      const anchors = res.data.filter((q: any) => q.question_type === 'anchor' && q.status === 'published')
      setDiagQuestions(anchors.slice(0, 15))
    } catch { setDiagQuestions([]) }
  }

  useEffect(() => {
    if (step !== 'diagnostic' || diagQuestions.length === 0) return
    setDiagTimer(30)
    const interval = setInterval(() => {
      setDiagTimer(t => {
        if (t <= 1) {
          handleDiagNext(true)
          return 30
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [diagIndex, step, diagQuestions.length])

  const handleConsent = async () => {
    setLoading(true)
    await api.post('/onboarding/consent')
    setStep('profile')
    setLoading(false)
  }

  const handleProfile = async () => {
    setLoading(true)
    await api.post('/onboarding/profile', profile)
    setStep('vark')
    setLoading(false)
  }

  const handleVarkAnswer = (type: string) => {
    const updated = { ...varkAnswers, [varkIndex]: type }
    setVarkAnswers(updated)
    if (varkIndex < VARK_QUESTIONS.length - 1) {
      setVarkIndex(varkIndex + 1)
    } else {
      submitVark(updated)
    }
  }

  const submitVark = async (answers: Record<number, string>) => {
    setLoading(true)
    const scores: Record<string, number> = { V: 0, A: 0, R: 0, K: 0 }
    Object.values(answers).forEach(t => { if (t in scores) scores[t]++ })
    const label = Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0]
    await api.post('/onboarding/vark', { scores, label })
    setStep('diagnostic')
    setLoading(false)
  }

  const handleDiagNext = (timeout = false) => {
    const q = diagQuestions[diagIndex]
    if (!q) return
    const ans = timeout ? null : selectedOption
    setDiagAnswers(prev => [...prev, {
      question_id: q.question_id,
      selected_option: ans,
      time_taken_sec: timeout ? 30 : 30 - diagTimer
    }])
    setSelectedOption('')
    if (diagIndex < diagQuestions.length - 1) {
      setDiagIndex(diagIndex + 1)
      setDiagTimer(30)
    } else {
      submitDiagnostic([...diagAnswers, { question_id: q.question_id, selected_option: ans, time_taken_sec: timeout ? 30 : 30 - diagTimer }])
    }
  }

  const submitDiagnostic = async (answers: any[]) => {
    setLoading(true)
    try { await api.post('/onboarding/diagnostic', { answers }) } catch {}
    setStep('complete')
    setLoading(false)
  }

  const progressSteps = ['consent', 'profile', 'vark', 'diagnostic', 'complete']
  const stepIndex = progressSteps.indexOf(step)

  return (
    <div className="min-h-screen bg-[#F8F9FC] flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8 justify-center">
          <div className="w-9 h-9 bg-[#003087] rounded-lg flex items-center justify-center text-white font-bold">L</div>
          <span className="text-xl font-bold text-[#003087]">LEARN</span>
        </div>

        {/* Progress */}
        {step !== 'complete' && (
          <div className="flex items-center justify-center gap-2 mb-8">
            {['Consent', 'Profile', 'VARK', 'Diagnostic'].map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all ${i < stepIndex ? 'bg-[#22C55E] text-white' : i === stepIndex ? 'bg-[#003087] text-white' : 'bg-[#E2E8F0] text-[#94A3B8]'}`}>
                  {i < stepIndex ? '✓' : i + 1}
                </div>
                <span className={`text-sm hidden sm:block ${i === stepIndex ? 'text-[#003087] font-semibold' : 'text-[#94A3B8]'}`}>{s}</span>
                {i < 3 && <div className={`w-8 h-0.5 ${i < stepIndex ? 'bg-[#22C55E]' : 'bg-[#E2E8F0]'}`}/>}
              </div>
            ))}
          </div>
        )}

        {/* Consent */}
        {step === 'consent' && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8">
            <h2 className="text-2xl font-bold text-[#1E293B] mb-2">Research Consent</h2>
            <p className="text-[#64748B] mb-6">Before you begin, please read and agree to the following:</p>
            <div className="bg-[#F8F9FC] rounded-xl p-5 mb-6 space-y-3 text-sm text-[#475569] leading-relaxed">
              <p>This platform is part of a research study conducted at <strong>SLIIT (Sri Lanka Institute of Information Technology)</strong>. Your participation helps improve adaptive English learning systems.</p>
              <p>During your learning journey, your interactions — including lesson time, quiz attempts, video/audio engagement, and scroll behavior — will be <strong>silently recorded</strong> for research analysis.</p>
              <p>All data is anonymised and used solely for academic research. Your personal identity will not be revealed in any publication.</p>
            </div>
            <div className="space-y-3 mb-8">
              <label className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" checked={consent1} onChange={e => setConsent1(e.target.checked)} className="mt-0.5 w-4 h-4 accent-[#003087]"/>
                <span className="text-sm text-[#475569]">I understand that my interactions are being recorded for research purposes.</span>
              </label>
              <label className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" checked={consent2} onChange={e => setConsent2(e.target.checked)} className="mt-0.5 w-4 h-4 accent-[#003087]"/>
                <span className="text-sm text-[#475569]">I understand that I can withdraw from this study at any time without penalty.</span>
              </label>
            </div>
            <button onClick={handleConsent} disabled={!consent1 || !consent2 || loading}
              className="w-full bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-3.5 rounded-xl transition-all">
              {loading ? 'Please wait...' : 'I Agree, Continue →'}
            </button>
          </div>
        )}

        {/* Profile */}
        {step === 'profile' && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8">
            <h2 className="text-2xl font-bold text-[#1E293B] mb-2">Your Profile</h2>
            <p className="text-[#64748B] mb-6">Help us understand your background so we can better analyse your learning journey.</p>
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-[#1E293B] mb-2">First Language</label>
                <div className="grid grid-cols-2 gap-2">
                  {['sinhala', 'tamil', 'english', 'other'].map(lang => (
                    <button key={lang} onClick={() => setProfile(p => ({ ...p, l1_language: lang }))}
                      className={`py-2.5 px-4 rounded-xl border-2 text-sm font-medium capitalize transition-all ${profile.l1_language === lang ? 'border-[#003087] bg-[#EFF6FF] text-[#003087]' : 'border-[#E2E8F0] text-[#64748B] hover:border-[#003087]'}`}>
                      {lang}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-[#1E293B] mb-2">Did you attend an English medium school?</label>
                <div className="grid grid-cols-2 gap-2">
                  {[{ label: 'Yes', val: true }, { label: 'No', val: false }].map(opt => (
                    <button key={opt.label} onClick={() => setProfile(p => ({ ...p, english_medium: opt.val }))}
                      className={`py-2.5 px-4 rounded-xl border-2 text-sm font-medium transition-all ${profile.english_medium === opt.val ? 'border-[#003087] bg-[#EFF6FF] text-[#003087]' : 'border-[#E2E8F0] text-[#64748B] hover:border-[#003087]'}`}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold text-[#1E293B] mb-2">How would you rate your English?</label>
                <div className="grid grid-cols-3 gap-2">
                  {['beginner', 'intermediate', 'advanced'].map(level => (
                    <button key={level} onClick={() => setProfile(p => ({ ...p, self_reported_level: level }))}
                      className={`py-2.5 px-4 rounded-xl border-2 text-sm font-medium capitalize transition-all ${profile.self_reported_level === level ? 'border-[#003087] bg-[#EFF6FF] text-[#003087]' : 'border-[#E2E8F0] text-[#64748B] hover:border-[#003087]'}`}>
                      {level}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <button onClick={handleProfile}
              disabled={!profile.l1_language || profile.english_medium === null || !profile.self_reported_level || loading}
              className="w-full mt-8 bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-3.5 rounded-xl transition-all">
              {loading ? 'Saving...' : 'Continue →'}
            </button>
          </div>
        )}

        {/* VARK */}
        {step === 'vark' && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-bold text-[#1E293B]">Learning Style Quiz</h2>
              <span className="text-sm text-[#64748B] font-medium">{varkIndex + 1} / {VARK_QUESTIONS.length}</span>
            </div>
            <div className="w-full bg-[#E2E8F0] rounded-full h-2 mb-6">
              <div className="bg-[#003087] h-2 rounded-full transition-all duration-300" style={{ width: `${((varkIndex) / VARK_QUESTIONS.length) * 100}%` }}/>
            </div>
            <p className="text-[#1E293B] text-lg leading-relaxed mb-6 font-medium">{VARK_QUESTIONS[varkIndex].q}</p>
            <div className="space-y-3">
              {Object.entries(VARK_QUESTIONS[varkIndex].options).map(([type, text]) => (
                <button key={type} onClick={() => handleVarkAnswer(type)}
                  className="w-full text-left py-3.5 px-5 rounded-xl border-2 border-[#E2E8F0] hover:border-[#003087] hover:bg-[#EFF6FF] text-[#475569] hover:text-[#003087] text-sm font-medium transition-all">
                  {text as string}
                </button>
              ))}
            </div>
            <p className="text-xs text-[#94A3B8] mt-4 text-center">You cannot go back to previous questions</p>
          </div>
        )}

        {/* Diagnostic */}
        {step === 'diagnostic' && diagQuestions.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-bold text-[#1E293B]">Level Check</h2>
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold ${diagTimer <= 10 ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-[#003087]'}`}>
                ⏱ {diagTimer}s
              </div>
            </div>
            <div className="w-full bg-[#E2E8F0] rounded-full h-2 mb-6">
              <div className="bg-[#FF6B00] h-2 rounded-full transition-all duration-300" style={{ width: `${(diagIndex / diagQuestions.length) * 100}%` }}/>
            </div>
            <p className="text-xs text-[#94A3B8] mb-4">Question {diagIndex + 1} of {diagQuestions.length} · No feedback will be shown</p>
            <p className="text-[#1E293B] text-lg leading-relaxed mb-6 font-medium">{diagQuestions[diagIndex]?.question_text}</p>
            <div className="space-y-3">
              {['A', 'B', 'C', 'D'].map(opt => {
                const text = diagQuestions[diagIndex]?.[`option_${opt.toLowerCase()}`]
                if (!text) return null
                return (
                  <button key={opt} onClick={() => setSelectedOption(opt)}
                    className={`w-full text-left py-3.5 px-5 rounded-xl border-2 text-sm font-medium transition-all ${selectedOption === opt ? 'border-[#003087] bg-[#EFF6FF] text-[#003087]' : 'border-[#E2E8F0] text-[#475569] hover:border-[#003087]'}`}>
                    <span className="font-bold mr-2">{opt}.</span>{text}
                  </button>
                )
              })}
            </div>
            <button onClick={() => handleDiagNext(false)} disabled={!selectedOption}
              className="w-full mt-6 bg-[#003087] hover:bg-[#0047c8] disabled:bg-[#E2E8F0] disabled:text-[#94A3B8] text-white font-semibold py-3.5 rounded-xl transition-all">
              {diagIndex < diagQuestions.length - 1 ? 'Next Question →' : 'Finish →'}
            </button>
          </div>
        )}

        {step === 'diagnostic' && diagQuestions.length === 0 && !loading && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8 text-center">
            <p className="text-[#64748B] mb-4">No diagnostic questions are ready yet. Skipping this step.</p>
            <button onClick={() => submitDiagnostic([])} className="bg-[#003087] text-white font-semibold py-3 px-6 rounded-xl">
              Continue to Dashboard →
            </button>
          </div>
        )}

        {/* Complete */}
        {step === 'complete' && (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E2E8F0] p-8 text-center">
            <div className="w-20 h-20 bg-[#DCFCE7] rounded-full flex items-center justify-center mx-auto mb-6">
              <span className="text-4xl">🎉</span>
            </div>
            <h2 className="text-2xl font-bold text-[#1E293B] mb-3">You're all set!</h2>
            <p className="text-[#64748B] mb-8">Your profile is ready. Time to start your English learning journey.</p>
            <button onClick={() => router.push('/learn')} className="bg-[#003087] hover:bg-[#0047c8] text-white font-semibold py-3.5 px-8 rounded-xl transition-all">
              Start Learning →
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  return <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="w-8 h-8 border-4 border-[#003087] border-t-transparent rounded-full animate-spin"/></div>}><OnboardingContent /></Suspense>
}