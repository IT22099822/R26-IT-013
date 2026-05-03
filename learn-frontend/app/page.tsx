'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function LandingPage() {
  const router = useRouter()

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.push('/learn')
    })
  }, [router])

  const [loginError, setLoginError] = useState<string | null>(null)

  const handleGoogleLogin = async () => {
    setLoginError(null)
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    })
    if (error) {
      console.error('Google sign-in failed:', error)
      setLoginError(error.message)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#001a4d] via-[#003087] to-[#0047c8] flex items-center justify-center p-4">
      <div className="max-w-5xl w-full grid md:grid-cols-2 gap-12 items-center">

        {/* Left — Branding */}
        <div className="text-white">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-[#FF6B00] rounded-xl flex items-center justify-center text-white font-bold text-xl">L</div>
            <span className="text-2xl font-bold tracking-tight">LEARN</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold leading-tight mb-6">
            Master English,<br />
            <span className="text-[#FF6B00]">One Step</span> at a Time
          </h1>
          <p className="text-blue-200 text-lg leading-relaxed mb-8">
            A structured English learning journey designed for SLIIT students. 
            Progress through 35 carefully crafted lessons at your own pace.
          </p>
          <div className="flex flex-wrap gap-4">
            {['35 Lessons', '4 Levels', 'Track Progress'].map(tag => (
              <span key={tag} className="bg-white/10 border border-white/20 text-white text-sm px-4 py-2 rounded-full">
                ✦ {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Right — Login Card */}
        <div className="bg-white rounded-2xl shadow-2xl p-8 md:p-10">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-[#1E293B] mb-2">Get Started</h2>
            <p className="text-[#64748B]">Sign in with your Google account to begin your learning journey.</p>
          </div>

          <div className="space-y-4 mb-8">
            {[
              { icon: '📋', title: 'Quick Onboarding', desc: 'Set up your profile in 5 minutes' },
              { icon: '📚', title: 'Structured Lessons', desc: 'Foundation to Advanced level content' },
              { icon: '🎯', title: 'Track Your Progress', desc: 'See your improvement over time' },
            ].map(item => (
              <div key={item.title} className="flex items-start gap-3">
                <span className="text-xl">{item.icon}</span>
                <div>
                  <p className="font-semibold text-[#1E293B] text-sm">{item.title}</p>
                  <p className="text-[#64748B] text-sm">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 bg-white border-2 border-[#E2E8F0] hover:border-[#003087] hover:shadow-lg text-[#1E293B] font-semibold py-3.5 px-6 rounded-xl transition-all duration-200"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          {loginError && (
            <p className="text-center text-sm text-red-600 mt-4 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
              {loginError}
            </p>
          )}

          <p className="text-center text-xs text-[#94A3B8] mt-6">
            By continuing, you agree to participate in the SLIIT research study.<br/>
            Your data is collected for academic research purposes only.
          </p>
        </div>

      </div>
    </div>
  )
}