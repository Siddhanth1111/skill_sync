import { Link } from 'react-router-dom'
import { Briefcase, FileCheck2, Gauge, Plus, Target } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { DataTable, PageHeader, StatCard } from '../../components/ui/Layout.jsx'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { BarChart } from '../../components/ui/Charts.jsx'
import { formatDate, pct } from '../../lib/utils.js'

export default function Dashboard() {
  const { user } = useAuth()
  const jobs = useApi(() => api.jobs())
  const overview = useApi(() => api.overview())
  const loading = jobs.loading || overview.loading
  const list = jobs.data || []
  const ov = overview.data

  const scoredJobs = ov?.jobs.filter((j) => j.scored > 0) || []
  const best = scoredJobs.length ? Math.max(...scoredJobs.map((j) => j.top_score)) : null
  const parsed = list.reduce((a, j) => a + j.parsed_count, 0)

  return (
    <>
      <PageHeader eyebrow="Recruiter" title={`Welcome${user.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}`}
        description="Your jobs, resumes and the requirements candidates struggle to meet."
        actions={<Link to="/recruiter/jobs/new"><Button leftIcon={<Plus />}>New job</Button></Link>} />
      <div className="flex flex-col gap-4 px-4">
        {(jobs.error || overview.error) && <ErrorState error={jobs.error || overview.error} onRetry={() => { jobs.reload(); overview.reload() }} />}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {loading ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />) : <>
            <StatCard label="Jobs" value={list.length} icon={Briefcase} />
            <StatCard label="Resumes parsed" value={parsed} icon={FileCheck2} />
            <StatCard label="Jobs scored" value={scoredJobs.length} icon={Target} hint={`${list.length - scoredJobs.length} not scored yet`} />
            <StatCard label="Best score" value={best == null ? '-' : pct(best)} icon={Gauge} hint="Out of 100, across all jobs" />
          </>}
        </div>

        <Card>
          <CardHeader title="Recent jobs" actions={list.length > 0 && <Link to="/recruiter/jobs"><Button variant="transparent" size="sm">View all</Button></Link>} />
          {loading ? <div className="p-4"><Skeleton className="h-24" /></div> : (
            <DataTable rows={list.slice(0, 5)} rowKey={(j) => j.id}
              columns={[
                { key: 'title', header: 'Job', render: (j) => <Link className="font-medium text-foreground hover:text-primary" to={`/recruiter/jobs/${j.id}`}>{j.title}</Link> },
                { key: 'req', header: 'Requirements', width: '8rem', align: 'right', render: (j) => j.requirements.length },
                { key: 'res', header: 'Resumes', width: '8rem', align: 'right', render: (j) => `${j.parsed_count} / ${j.candidate_count}` },
                { key: 'created', header: 'Created', width: '9rem', render: (j) => formatDate(j.created_at) },
              ]}
              empty={<EmptyState icon={Briefcase} title="No jobs yet" action={<Link to="/recruiter/jobs/new"><Button>Create your first job</Button></Link>}>Paste a job description to turn it into requirements you can score resumes against.</EmptyState>} />
          )}
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader title="Requirements candidates miss most" description="Across your scored jobs" />
            <div className="p-4">
              {ov?.common_gaps.length ? (
                <ul className="flex flex-col gap-2.5 text-sm">{ov.common_gaps.slice(0, 6).map((g) => (
                  <li key={g.text} className="flex items-center justify-between gap-3"><span className="min-w-0 truncate">{g.text}</span><span className="shrink-0 tabular-nums text-muted-foreground">{g.count} candidates</span></li>
                ))}</ul>
              ) : <p className="text-sm text-muted-foreground">No scored jobs yet. Score a job to see where candidates fall short.</p>}
            </div>
          </Card>
          <Card>
            <CardHeader title="Skills in demand" description="How many of your jobs ask for each skill" />
            <div className="p-4">
              {ov?.skill_demand.length ? <BarChart data={ov.skill_demand.slice(0, 8).map((s) => ({ label: s.skill, value: s.jobs }))} height={140} />
                : <p className="text-sm text-muted-foreground">Skills appear here once a job has requirements that name them.</p>}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
