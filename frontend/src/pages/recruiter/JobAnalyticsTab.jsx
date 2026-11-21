import { useOutletContext, Link } from 'react-router-dom'
import { BarChart3, Gauge, Layers, Users } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { BarChart, StackedBar } from '../../components/ui/Charts.jsx'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { DataTable, StatCard } from '../../components/ui/Layout.jsx'
import { ImportanceBadge } from '../../components/ui/Badge.jsx'
import { pct } from '../../lib/utils.js'

export default function JobAnalyticsTab() {
  const { job } = useOutletContext()
  const a = useApi(() => api.jobAnalytics(job.id), [job.id])
  if (a.error) return <ErrorState error={a.error} onRetry={a.reload} />
  if (a.loading) return <Skeleton className="h-64" />
  const d = a.data
  if (!d.scored) return <Card><EmptyState icon={BarChart3} title="Nothing to analyse yet">Score this job to see score distribution, requirement coverage and near matches.</EmptyState></Card>

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Scored" value={d.scored} icon={Users} hint={`${d.parsed} resumes parsed`} />
        <StatCard label="Mean score" value={pct(d.mean_score)} icon={Gauge} hint="Out of 100" />
        <StatCard label="Top score" value={pct(d.top_score)} icon={Gauge} />
        <StatCard label="One step away" value={d.one_away.length} icon={Layers} hint="Missing exactly one requirement" />
      </div>
      {d.quality && d.quality.cells > 0 && (
        <Card><CardHeader title="Scoring quality on this job" description="Measured on these resumes. These are checks on the evidence, not accuracy against human judgement." />
          <dl className="grid grid-cols-2 gap-4 p-4 text-sm lg:grid-cols-4">
            <div><dt className="text-xs text-muted-foreground">Requirements with verified evidence</dt><dd className="text-lg font-medium tabular-nums">{d.quality.verified_rate == null ? '-' : `${pct(d.quality.verified_rate)}%`}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Evidence reused too often</dt><dd className="text-lg font-medium tabular-nums">{d.quality.evidence_reuse_rate == null ? '-' : `${pct(d.quality.evidence_reuse_rate)}%`}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Weak evidence</dt><dd className="text-lg font-medium tabular-nums">{d.quality.weak_evidence_rate == null ? '-' : `${pct(d.quality.weak_evidence_rate)}%`}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Not verifiable (poor scan)</dt><dd className="text-lg font-medium tabular-nums">{d.quality.unverifiable_rate == null ? '-' : `${pct(d.quality.unverifiable_rate)}%`}</dd></div>
          </dl>
          <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">{d.scored_requirements} scored requirements{d.unscored_requirements ? `, ${d.unscored_requirements} listed but not scored` : ''}. Pipeline {d.quality.pipeline_versions.join(', ') || '-'}.</p>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader title="Score distribution" description="Candidates per 10-point band" />
          <div className="p-4"><BarChart height={150} data={d.histogram.map((h) => ({ label: `${h.from * 100}`, value: h.count, title: `${h.from * 100} to ${h.to * 100}` }))} /></div></Card>
        <Card><CardHeader title="Tiers" description="Strong 75 and above, moderate 50 to 74, low under 50" />
          <div className="p-4"><StackedBar parts={[{ label: 'Strong', value: d.tiers.strong, tone: 'success' }, { label: 'Moderate', value: d.tiers.moderate, tone: 'warning' }, { label: 'Low', value: d.tiers.low, tone: 'destructive' }]} /></div></Card>
      </div>
      <Card><CardHeader title="Requirement coverage" description="Share of scored candidates who meet each requirement" />
        <DataTable rows={d.coverage} rowKey={(c) => c.requirement_id} columns={[
          { key: 't', header: 'Requirement', render: (c) => c.text },
          { key: 'i', header: 'Importance', width: '7rem', render: (c) => <ImportanceBadge importance={c.importance} /> },
          { key: 'bar', header: 'Met', width: '14rem', render: (c) => <div className="flex items-center gap-2"><div className="h-2 flex-1 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-success" style={{ width: `${c.share_met * 100}%` }} /></div><span className="w-10 text-right tabular-nums">{pct(c.share_met)}%</span></div> },
          { key: 'c', header: 'Met / partial / not met', width: '11rem', align: 'right', render: (c) => `${c.met} / ${c.partial} / ${c.not_met}` },
        ]} /></Card>
      <Card><CardHeader title="One requirement away" description="Candidates who meet everything except one requirement" />
        <DataTable rows={d.one_away} rowKey={(o) => o.candidate_id} columns={[
          { key: 'n', header: 'Candidate', render: (o) => <Link className="font-medium hover:text-primary" to={`/recruiter/jobs/${job.id}/ranking?candidate=${o.candidate_id}`}>{o.name}</Link> },
          { key: 'm', header: 'Missing', render: (o) => o.missing }, { key: 'i', header: 'Importance', width: '7rem', render: (o) => <ImportanceBadge importance={o.importance} /> },
        ]} empty={<p className="px-4 py-6 text-sm text-muted-foreground">No candidate is exactly one requirement short.</p>} /></Card>
    </div>
  )
}
