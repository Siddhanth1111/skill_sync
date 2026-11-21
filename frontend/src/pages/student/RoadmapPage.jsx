import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, FlaskConical } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge, SourceBadge, StatusBadge } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { Alert, EmptyState, ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { Textarea } from '../../components/ui/Form.jsx'
import { PageHeader, StatCard } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import { num } from '../../lib/utils.js'
import { useResume } from './useResume.js'

const PHASES = [['start_here', 'Start here', 'Must-haves. These cost the most points.'], ['next', 'Next', 'Should-haves.'], ['later', 'Later', 'Nice-to-haves.']]

export default function RoadmapPage() {
  const { jobId } = useParams()
  const resume = useResume()
  const cid = resume.data?.status === 'done' ? resume.data.id : null
  const rm = useApi(() => api.roadmap(cid, jobId), [cid, jobId], { enabled: !!cid })
  const toast = useToast()
  const [addition, setAddition] = useState('')
  const [sim, setSim] = useState(null)
  const [busy, setBusy] = useState(false)

  const simulate = async (e) => {
    e.preventDefault()
    setBusy(true)
    try { setSim(await api.whatIf(cid, jobId, addition)) } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }

  const d = rm.data
  return (
    <>
      <PageHeader eyebrow={<Link to="/student/matches" className="inline-flex items-center gap-0.5 hover:text-foreground"><ChevronLeft className="size-3" />Matches</Link>}
        title={d ? d.title : 'Roadmap'} description="The order that raises your score the most, with a running projected score." />
      <div className="flex flex-col gap-4 px-4">
        {rm.error && (rm.error.status === 409
          ? <Alert color="warning" title="Run the match first">This job has not been scored against your resume. <Link className="underline" to="/student/matches">Go to Matches</Link></Alert>
          : <ErrorState error={rm.error} onRetry={rm.reload} />)}
        {rm.loading && <Skeleton className="h-48" />}
        {d && <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            <StatCard label="Your score now" value={num(d.current_score * 100, 0)} hint="Out of 100" />
            <StatCard label="If you close every gap" value={num(d.final_projected_score * 100, 0)} hint={`${d.steps.length} step${d.steps.length === 1 ? '' : 's'}`} />
            <StatCard label="Potential gain" value={`+${num((d.final_projected_score - d.current_score) * 100, 0)}`} hint="Points" />
          </div>

          {d.steps.length === 0 ? <Card><EmptyState title="Every requirement is met">There is nothing left to improve for this job.</EmptyState></Card> : PHASES.map(([phase, title, hint]) => {
            const steps = d.steps.filter((s) => s.phase === phase)
            if (!steps.length) return null
            return (
              <Card key={phase}>
                <CardHeader title={title} description={hint} />
                <ol className="divide-y divide-border">
                  {steps.map((s) => (
                    <li key={s.requirement_id} className="flex flex-col gap-2 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={s.status} /><p className="font-medium">{s.text}</p>
                        <span className="ml-auto text-xs tabular-nums text-muted-foreground"><b className="text-primary">+{s.points_gain.toFixed(1)}</b> points · projected {num(s.projected_score * 100, 0)}</span>
                      </div>
                      <p className="text-sm text-muted-foreground">{s.action} <SourceBadge source={s.action_source === 'llm' ? 'llm' : 'rules'} label={s.action_source === 'llm' ? 'Language model' : 'Template'} /></p>
                    </li>
                  ))}
                </ol>
              </Card>
            )
          })}

          <Card>
            <CardHeader title="What if...? (an estimate)" description="Describe in a full sentence something you built or did, ideally with a result. Your resume is rescored as if it were there, assuming it is true. Nothing is saved." />
            <form onSubmit={simulate} className="flex flex-col gap-3 p-4">
              <Textarea rows={3} required minLength={20} value={addition} onChange={(e) => setAddition(e.target.value)} aria-label="Project or skill to add"
                placeholder="Built a Tableau dashboard analysing 5 years of sales data" />
              <div><Button type="submit" leftIcon={<FlaskConical />} loading={busy} disabled={addition.trim().split(/\s+/).length < 6}>Simulate</Button></div>
            </form>
            {sim && (
              <div className="border-t border-border p-4">
                <p className="text-sm">Score <b className="tabular-nums">{num(sim.before * 100)}</b> to <b className="tabular-nums">{num(sim.after * 100)}</b>{' '}
                  <Badge color={sim.delta_points > 0 ? 'success' : 'neutral'}>{sim.delta_points >= 0 ? '+' : ''}{num(sim.delta_points)} points</Badge> <span className="text-xs text-muted-foreground">Nothing was saved.</span></p>
                  {sim.note && <p className="mt-1 text-xs text-muted-foreground">{sim.note}</p>}
                {sim.changes.length > 0 ? <ul className="mt-2 flex flex-col gap-1 text-sm">{sim.changes.map((c) => <li key={c.requirement_id} className="flex gap-2"><span className="w-24 shrink-0 tabular-nums text-muted-foreground">{num(c.before * 100, 0)} to {num(c.after * 100, 0)}</span>{c.text}</li>)}</ul>
                  : <p className="mt-2 text-sm text-muted-foreground">No requirement changed. The addition does not touch what this job asks for.</p>}
              </div>
            )}
          </Card>
        </>}
      </div>
    </>
  )
}
