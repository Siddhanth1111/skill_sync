import { Link } from 'react-router-dom'
import { Activity, Briefcase, FileText, Users } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { PageHeader, StatCard } from '../../components/ui/Layout.jsx'
import { Alert } from '../../components/ui/Feedback.jsx'

export default function AdminOverview() {
  const stats = useApi(() => api.adminStats())
  const s = stats.data
  return (
    <>
      <PageHeader eyebrow="Admin" title="Overview" description="Accounts and activity. Admins cannot open recruiters' or students' resumes." />
      <div className="flex flex-col gap-4 px-4">
        {stats.error && <ErrorState error={stats.error} onRetry={stats.reload} />}
        {stats.loading ? <Skeleton className="h-24" /> : s && (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Users" value={s.users} icon={Users} hint={Object.entries(s.by_role).map(([r, n]) => `${n} ${r}`).join(', ')} />
            <StatCard label="Jobs" value={s.jobs} icon={Briefcase} /><StatCard label="Resumes" value={s.candidates} icon={FileText} />
            <StatCard label="Activity" value="Log" icon={Activity} hint="See every action" />
          </div>
        )}
        <Card><CardHeader title="Manage" />
          <div className="grid gap-px bg-border sm:grid-cols-2">
            <Link to="/admin/users" className="bg-card p-4 hover:bg-muted/40"><p className="font-medium">Users</p><p className="text-sm text-muted-foreground">See accounts, last sign-in and data volume. Remove a user with all of their data.</p></Link>
            <Link to="/admin/activity" className="bg-card p-4 hover:bg-muted/40"><p className="font-medium">Activity log</p><p className="text-sm text-muted-foreground">Sign-ins, uploads, scoring runs, audits and deletions.</p></Link>
          </div>
        </Card>
        <Alert>The activity log records action names, ids and counts only. It never contains resume text or personal data.</Alert>
      </div>
    </>
  )
}
