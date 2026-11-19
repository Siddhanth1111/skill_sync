import { Link } from 'react-router-dom'
import { ArrowRight, Briefcase, CheckCircle2, Circle, FileText, Target } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { PageHeader, StatCard } from '../../components/ui/Layout.jsx'
import { cn, pct } from '../../lib/utils.js'
import { useResume } from './useResume.js'

export default function Overview() {
  const { user } = useAuth()
  const resume = useResume()
  const jobs = useApi(() => api.jobs())
  const matches = useApi(() => api.studentMatches())
  const hasResume = resume.data?.status === 'done'
  const nJobs = jobs.data?.length || 0
  const best = matches.data?.[0]

  const steps = [
    { done: hasResume, icon: FileText, title: 'Upload your resume', body: 'A PDF or DOCX. It is read, structured and indexed.', to: '/student/resume', cta: hasResume ? 'View' : 'Upload' },
    { done: nJobs > 0, icon: Briefcase, title: 'Add job descriptions', body: 'Paste the jobs you are interested in. Each becomes a list of requirements.', to: '/student/jobs', cta: nJobs ? 'Manage' : 'Add' },
    { done: !!matches.data?.length, icon: Target, title: 'Match and plan', body: 'See how your resume scores for each job, and what to do next.', to: '/student/matches', cta: matches.data?.length ? 'Open' : 'Match' },
  ]
  return (
    <>
      <PageHeader eyebrow="Student" title={`Welcome${user.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}`} description="Find out how well your resume matches the jobs you want, and what would improve it." />
      <div className="flex flex-col gap-4 px-4">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <StatCard label="Resume" value={hasResume ? 'Ready' : resume.data ? 'Parsing' : 'None'} icon={FileText} />
          <StatCard label="Jobs added" value={nJobs} icon={Briefcase} />
          <StatCard label="Best match" value={best ? pct(best.final_score) : '-'} icon={Target} hint={best ? best.title : 'Run a match to see scores'} />
        </div>
        <Card>
          <ol className="divide-y divide-border">
            {steps.map((s, i) => (
              <li key={s.title} className="flex items-center gap-4 px-4 py-4">
                {s.done ? <CheckCircle2 className="size-5 shrink-0 text-success" aria-label="Done" /> : <Circle className="size-5 shrink-0 text-muted-foreground" aria-label="To do" />}
                <div className="min-w-0 flex-1"><p className={cn('font-medium', s.done && 'text-muted-foreground')}>{i + 1}. {s.title}</p><p className="text-sm text-muted-foreground">{s.body}</p></div>
                <Link to={s.to}><Button variant={s.done ? 'outline' : 'primary'} rightIcon={<ArrowRight />}>{s.cta}</Button></Link>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </>
  )
}
