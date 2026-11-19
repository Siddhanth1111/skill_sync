import { Link } from 'react-router-dom'
import { BarChart3, ThumbsUp, Users } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { BarChart } from '../../components/ui/Charts.jsx'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { DataTable, PageHeader, StatCard } from '../../components/ui/Layout.jsx'
import { pct } from '../../lib/utils.js'

export default function AnalyticsOverview() {
  const a = useApi(() => api.overview())
  const d = a.data
  return (
    <>
      <PageHeader title="Analytics" description="Across all of your jobs: scores, common gaps and strengths, skill demand, and how much you have rated." />
      <div className="flex flex-col gap-4 px-4">
        {a.error && <ErrorState error={a.error} onRetry={a.reload} />}
        {a.loading && <Skeleton className="h-64" />}
        {d && (!d.jobs.length ? <Card><EmptyState icon={BarChart3} title="No jobs to analyse" action={<Link className="text-primary hover:underline" to="/recruiter/jobs/new">Create a job</Link>}>Analytics appear after you create and score a job.</EmptyState></Card> : <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Resumes" value={d.labelling.candidates} icon={Users} />
            <StatCard label="Rated" value={d.labelling.rated} icon={ThumbsUp} hint={`${d.labelling.up} good fit, ${d.labelling.down} not a fit`} />
            <StatCard label="Labelling done" value={d.labelling.candidates ? `${Math.round((d.labelling.rated / d.labelling.candidates) * 100)}%` : '-'} hint="Share of resumes rated" />
            <StatCard label="Jobs" value={d.jobs.length} />
          </div>
          <Card><CardHeader title="Jobs" />
            <DataTable rows={d.jobs} rowKey={(j) => j.job_id} columns={[
              { key: 't', header: 'Job', render: (j) => <Link className="font-medium hover:text-primary" to={`/recruiter/jobs/${j.job_id}/analytics`}>{j.title}</Link> },
              { key: 'p', header: 'Parsed', width: '6rem', align: 'right', render: (j) => j.parsed }, { key: 's', header: 'Scored', width: '6rem', align: 'right', render: (j) => j.scored },
              { key: 'm', header: 'Mean score', width: '8rem', align: 'right', render: (j) => pct(j.mean_score) }, { key: 'b', header: 'Top score', width: '8rem', align: 'right', render: (j) => pct(j.top_score) },
            ]} /></Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader title="Most common gaps" description="Requirements fewer than half of candidates fully meet" />
              <div className="p-4">{d.common_gaps.length ? <ul className="flex flex-col gap-2 text-sm">{d.common_gaps.map((g) => <li key={g.text} className="flex justify-between gap-3"><span>{g.text}</span><span className="shrink-0 tabular-nums text-muted-foreground">{g.count}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">None yet.</p>}</div></Card>
            <Card><CardHeader title="Most common strengths" description="Requirements at least half of candidates meet" />
              <div className="p-4">{d.common_strengths.length ? <ul className="flex flex-col gap-2 text-sm">{d.common_strengths.map((g) => <li key={g.text} className="flex justify-between gap-3"><span>{g.text}</span><span className="shrink-0 tabular-nums text-muted-foreground">{g.count}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">None yet.</p>}</div></Card>
          </div>
          <Card><CardHeader title="Skill demand" description="Skills named in requirements, by number of jobs" />
            <div className="p-4"><BarChart height={160} data={d.skill_demand.map((s) => ({ label: s.skill, value: s.jobs }))} /></div></Card>
        </>)}
      </div>
    </>
  )
}
