'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import { tracker } from '@/lib/tracker'

const navItems = [
  { href: '/learn', icon: '📚', label: 'Dashboard' },
  { href: '/progress', icon: '📊', label: 'My Progress' },
  { href: '/notifications', icon: '🔔', label: 'Notifications' },
]

export default function Sidebar({ userName = '' }: { userName?: string }) {
  const pathname = usePathname()
  const router = useRouter()

  const handleLogout = async () => {
    const sessionId = localStorage.getItem('session_id')
    tracker.stopHeartbeat()
    try { if (sessionId) await api.post('/auth/logout', { session_id: sessionId }) } catch {}
    await supabase.auth.signOut()
    localStorage.removeItem('session_id')
    router.push('/')
  }

  return (
    <aside className="w-64 min-h-screen bg-white border-r border-[#E2E8F0] flex flex-col fixed left-0 top-0">
      <div className="p-6 border-b border-[#E2E8F0]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-[#003087] rounded-lg flex items-center justify-center text-white font-bold text-sm">L</div>
          <div>
            <p className="font-bold text-[#003087] text-sm">LEARN</p>
            <p className="text-xs text-[#94A3B8]">SLIIT Research</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {navItems.map(item => (
          <Link key={item.href} href={item.href}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${pathname === item.href || pathname.startsWith(item.href + '/') ? 'bg-[#EFF6FF] text-[#003087]' : 'text-[#64748B] hover:bg-[#F8F9FC] hover:text-[#1E293B]'}`}>
            <span>{item.icon}</span>{item.label}
          </Link>
        ))}
      </nav>

      <div className="p-4 border-t border-[#E2E8F0]">
        {userName && (
          <div className="flex items-center gap-3 px-3 py-2 mb-2">
            <div className="w-8 h-8 bg-[#003087] rounded-full flex items-center justify-center text-white text-xs font-bold">
              {userName.charAt(0).toUpperCase()}
            </div>
            <p className="text-sm text-[#1E293B] font-medium truncate">{userName}</p>
          </div>
        )}
        <button onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-[#64748B] hover:bg-red-50 hover:text-red-600 transition-all">
          <span>🚪</span> Logout
        </button>
      </div>
    </aside>
  )
}