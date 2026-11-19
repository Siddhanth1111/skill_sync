import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, Briefcase, FileText, LayoutDashboard, LogOut, Menu, Search, Settings, ShieldCheck, Target, Users, X } from 'lucide-react'
import { useAuth } from '../auth/AuthContext.jsx'
import { Avatar } from './ui/Avatar.jsx'
import { Badge } from './ui/Badge.jsx'
import { Button } from './ui/Button.jsx'
import { cn } from '../lib/utils.js'

const NAV = {
  recruiter: [
    { to: '/recruiter', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/recruiter/jobs', label: 'Jobs', icon: Briefcase },
    { to: '/recruiter/search', label: 'Search resumes', icon: Search },
    { to: '/recruiter/analytics', label: 'Analytics', icon: BarChart3 },
  ],
  student: [
    { to: '/student', label: 'Overview', icon: LayoutDashboard, end: true },
    { to: '/student/resume', label: 'My resume', icon: FileText },
    { to: '/student/jobs', label: 'Job descriptions', icon: Briefcase },
    { to: '/student/matches', label: 'Matches and roadmap', icon: Target },
  ],
  admin: [
    { to: '/admin', label: 'Overview', icon: ShieldCheck, end: true },
    { to: '/admin/users', label: 'Users', icon: Users },
    { to: '/admin/activity', label: 'Activity log', icon: Activity },
  ],
}

function NavItem({ item, onNavigate }) {
  const Icon = item.icon
  return (
    <NavLink to={item.to} end={item.end} onClick={onNavigate}
      className={({ isActive }) => cn('flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm',
        isActive ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground' : 'text-sidebar-foreground hover:bg-muted-hover')}>
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </NavLink>
  )
}

function SidebarContent({ onNavigate }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const items = NAV[user.role] || []
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 px-4">
        <span className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">S</span>
        <span className="text-base font-semibold text-foreground">SkillSync</span>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2" aria-label="Main">
        {items.map((it) => <NavItem key={it.to} item={it} onNavigate={onNavigate} />)}
      </nav>
      <div className="border-t border-sidebar-border p-2">
        <NavItem item={{ to: '/settings', label: 'Settings', icon: Settings }} onNavigate={onNavigate} />
        <div className="mt-2 flex items-center gap-2 rounded-md px-2 py-2">
          <Avatar name={user.full_name || user.email} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-foreground">{user.full_name || user.email}</p>
            <Badge color="neutral" className="mt-0.5 capitalize">{user.role}</Badge>
          </div>
          <Button variant="transparent" iconOnly aria-label="Sign out" onClick={() => { signOut(); navigate('/login') }}><LogOut /></Button>
        </div>
      </div>
    </div>
  )
}

export default function AppShell() {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex h-full bg-background">
      <aside className="hidden w-60 shrink-0 border-r border-sidebar-border bg-sidebar md:block">
        <SidebarContent />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 flex bg-overlay md:hidden" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
          <aside className="w-64 bg-sidebar shadow-md"><SidebarContent onNavigate={() => setOpen(false)} /></aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 border-b border-border bg-card px-3 md:hidden">
          <Button variant="transparent" iconOnly aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</Button>
          <span className="text-base font-semibold">SkillSync</span>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl pb-8"><Outlet /></div>
        </main>
      </div>
    </div>
  )
}
