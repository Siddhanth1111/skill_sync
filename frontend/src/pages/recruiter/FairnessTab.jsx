import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Eye, GitCompare, Scale, Sigma } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { TrendChart } from '../../components/ui/Charts.jsx'
import { Alert, EmptyState } from '../../components/ui/Feedback.jsx'
import { Input, Select } from '../../components/ui/Form.jsx'
import { DataTable } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import { cn, formatDateTime, num } from '../../lib/utils.js'

function Audit({ icon: Icon, title, body, children, action }) {
  return (
    <Card className="flex flex-col">
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center gap-2"><Icon className="size-4 text-muted-foreground" aria-hidden /><h3 className="font-medium">{title}</h3></div>
        <p className="text-sm text-muted-foreground">{body}</p>
        {children}
      </div>
      <div className="border-t border-border p-3">{action}</div>
    </Card>
  )
}

export default function FairnessTab() {
  const { job } = useOutletContext()
  const toast = useToast()
  const matrix = useApi(() => api.matrix(job.id), [job.id])
  const history = useApi(() => api.auditHistory(job.id), [job.id])
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState(null)
  // Group labels are never made up. They are typed in or pasted from consented, self-reported data, or the audit is
  // run as a clearly marked demo with example labels.
  const [labels, setLabels] = useState({})
  const [consent, setConsent] = useState(false)
  const [demo, setDemo] = useState(false)
  const [topN, setTopN] = useState(3)
  const [weat, setWeat] = useState('gender')

  const scored = useMemo(() => (matrix.data?.candidates || []).filter((c) => c.scored), [matrix.data])
  const filled = scored.filter((c) => (labels[c.id] || '').trim())
  const distinct = new Set(filled.map((c) => labels[c.id].trim())).size
  const canImpact = filled.length >= 2 && distinct >= 2 && (consent || demo)
  const loadDemo = () => { setLabels(Object.fromEntries(scored.map((c, i) => [c.id, i % 2 ? 'Demo B' : 'Demo A']))); setDemo(true); setConsent(false) }
  const onLabel = (id, v) => { setLabels((l) => ({ ...l, [id]: v })); if (demo) setDemo(false) }

  const run = async (kind, body) => {
    setBusy(kind)
    try { setResult({ kind, data: await api.audit(job.id, kind, body) }); await history.reload(true) }
    catch (e) { toast.error(e.message) } finally { setBusy('') }
  }
  const reopen = async (h) => {
    try { setResult({ kind: h.kind, data: await api.auditDetail(job.id, h.audit_id) }) } catch (e) { toast.error(e.message) }
  }

  if (matrix.loading) return null
  if (!scored.length) return <Card><EmptyState icon={Scale} title="Score this job first">Audits compare against stored scores. Run scoring on the Ranking tab.</EmptyState></Card>

  const byKind = {}
  ;(history.data || []).forEach((h) => { (byKind[h.kind] ||= []).push({ id: h.audit_id, value: h.headline?.value, label: h.headline?.label }) })

  return (
    <div className="flex flex-col gap-4">
      <Alert color="warning" title="What these audits can and cannot tell you">
        They use consented group labels (or a marked demo) and simple text changes. They do not cover every proxy, such as address or employment gaps, and passing them is not proof of fairness. Resumes are scored with names, contact details, schools and pronouns removed by default; the blind audit shows what that changes. Use a flag to decide where a person should look.
      </Alert>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Audit icon={Eye} title="Blind mode" body="Scores every resume twice through the same pipeline, with identity details present and removed (name, contact, links, postcode, school, education years, pronouns), and compares the order."
          action={<Button variant="outline" loading={busy === 'blind'} disabled={!!busy} onClick={() => run('blind')}>Run blind audit</Button>} />
        <Audit icon={GitCompare} title="Counterfactual swap" body="Changes one thing that should not matter (name and pronouns, school, date format) and flags a score change above 2 points out of 100. With blind scoring on, name, pronoun and school changes should show no change."
          action={<Button variant="outline" loading={busy === 'counterfactual'} disabled={!!busy} onClick={() => run('counterfactual')}>Run counterfactual</Button>} />
        <Audit icon={Scale} title="Adverse impact" body="Selection means being in the top N. A group whose rate is under 0.8 of the best group's rate is flagged."
          action={<Button variant="outline" loading={busy === 'impact'} disabled={!!busy || !canImpact} onClick={() => run('impact', { groups: Object.fromEntries(filled.map((c) => [String(c.id), labels[c.id].trim()])), top_n: topN, consent, demo })}>Run impact ratio</Button>}>
          <label className="mt-1 flex items-center gap-2 text-sm">Top N <Input type="number" min="1" max={scored.length} value={topN} onChange={(e) => setTopN(Math.max(1, Number(e.target.value)))} className="h-8 w-20 tabular-nums" /></label>
        </Audit>
        <Audit icon={Sigma} title="WEAT probe" body="Tests the embedding model for biased associations between two name groups and pleasant or unpleasant words."
          action={<Button variant="outline" loading={busy === 'weat'} disabled={!!busy} onClick={() => run('weat', { groups: weat })}>Run WEAT</Button>}>
          <Select value={weat} onChange={(e) => setWeat(e.target.value)} className="mt-1 h-8" aria-label="Name groups"><option value="gender">Male-coded vs female-coded names</option><option value="origin">Anglo vs Indian names</option></Select>
        </Audit>
      </div>

      <details className="rounded-lg bg-card shadow-sm" open={!canImpact}>
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium">Group labels for the impact audit <span className="font-normal text-muted-foreground">({filled.length} of {scored.length} labelled)</span></summary>
        <div className="flex flex-col gap-3 border-t border-border p-4">
          <p className="text-sm text-muted-foreground">SkillSync never guesses or generates group membership. Enter labels only if they are self-reported and consented, such as from an application form with a voluntary question. Otherwise run the audit as a demo to see how it works.</p>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 accent-primary" checked={consent} onChange={(e) => { setConsent(e.target.checked); if (e.target.checked) setDemo(false) }} />
            <span>These labels are self-reported and the candidates consented to this use.</span></label>
          <div className="flex items-center gap-2"><Button variant="outline" size="sm" onClick={loadDemo}>Fill with demo labels</Button>{demo && <Badge color="warning" dot>Demo: the report will be marked as not real data</Badge>}</div>
        </div>
        <div className="border-t border-border">
          <DataTable rows={scored} rowKey={(c) => c.id} columns={[
            { key: 'n', header: 'Candidate', render: (c) => c.name || c.filename },
            { key: 'g', header: 'Group', width: '12rem', render: (c) => <Input value={labels[c.id] || ''} onChange={(e) => onLabel(c.id, e.target.value)} className="h-8" placeholder="not labelled" aria-label={`Group for ${c.name || c.filename}`} /> },
          ]} />
        </div>
      </details>

      {result && <AuditResult kind={result.kind} data={result.data} />}

      <Card>
        <CardHeader title="Monitoring over time" description="Every audit run is saved. Open a past run to read its report." />
        <div className="p-4">
          {!history.data?.length ? <p className="text-sm text-muted-foreground">No audits yet.</p> : (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{Object.entries(byKind).map(([k, pts]) => <TrendChart key={k} label={`${k}: ${pts[0].label || 'headline value'}`} points={pts} />)}</div>
              <ul className="divide-y divide-border rounded-md border border-border text-sm">
                {[...history.data].reverse().slice(0, 8).map((h) => (
                  <li key={h.audit_id} className="flex items-center gap-3 px-3 py-2">
                    <Badge color="neutral" className="capitalize">{h.kind}</Badge>
                    <span className="flex-1 text-muted-foreground">{formatDateTime(h.created_at)}</span>
                    <span className="tabular-nums">{h.headline?.value == null ? '-' : num(h.headline.value, 2)} <span className="text-xs text-muted-foreground">{h.headline?.label}</span></span>
                    <Button variant="transparent" size="sm" onClick={() => reopen(h)}>Open</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

function AuditResult({ kind, data }) {
  const flag = (row) => row.flagged || row.rank_normal !== row.rank_blind
  return (
    <Card>
      <CardHeader title={{ blind: 'Blind mode result', counterfactual: 'Counterfactual result', impact: 'Adverse impact result', weat: 'WEAT result' }[kind]} />
      <div className="flex flex-col gap-3 p-4">
        {kind === 'blind' && <>
          <p className="text-sm">Scoring mode: <b>{data.scoring_mode}</b>. Average change <b className="tabular-nums">{num(data.avg_change, 2)}</b> points (absolute {num(data.avg_abs_change, 2)}). <b>{data.rank_changes}</b> of {data.candidates.length} candidates changed rank.</p>
          <DataTable rows={data.candidates} rowKey={(c) => c.candidate_id} columns={[
            { key: 'n', header: 'Candidate', render: (c) => c.name },
            { key: 'a', header: 'Normal', align: 'right', render: (c) => num(c.normal) }, { key: 'b', header: 'Blind', align: 'right', render: (c) => num(c.blind) },
            { key: 'c', header: 'Change', align: 'right', render: (c) => num(c.change, 2) },
            { key: 'r', header: 'Rank', align: 'right', render: (c) => <span className={cn(flag(c) && 'font-medium text-warning-text')}>{c.rank_normal} to {c.rank_blind}</span> },
          ]} /></>}
        {kind === 'counterfactual' && <>
          <p className="text-sm"><b>{data.flagged_count}</b> candidate{data.flagged_count === 1 ? '' : 's'} flagged (change above {data.threshold_points} points). Largest change {num(data.max_abs_change, 2)} points.</p>
          <DataTable rows={data.candidates} rowKey={(c) => c.candidate_id} columns={[
            { key: 'n', header: 'Candidate', render: (c) => c.name },
            { key: 'm', header: 'Male-name variant', align: 'right', render: (c) => num(c.change_male_variant, 2) },
            { key: 'f', header: 'Female-name variant', align: 'right', render: (c) => num(c.change_female_variant, 2) },
            { key: 's', header: 'School swap', align: 'right', render: (c) => num(c.change_school_variant, 2) },
            { key: 'd', header: 'Date format', align: 'right', render: (c) => num(c.change_date_format_variant, 2) },
            { key: 'x', header: 'Result', render: (c) => c.flagged ? <Badge color="warning" dot>Flagged</Badge> : <Badge color="success" dot>Within 2 points</Badge> },
          ]} /></>}
        {kind === 'impact' && <>
          {data.warning && <Alert color="warning">{data.warning}</Alert>}
          <p className="text-sm">Top {data.top_n} of {data.n_candidates} selected. Demographic parity difference (Fairlearn): <b className="tabular-nums">{num(data.demographic_parity_difference, 3)}</b>. {data.flagged_groups.length ? <>Flagged below {data.ratio_threshold}: <b>{data.flagged_groups.join(', ')}</b>.</> : 'No group is below the threshold.'}</p>
          <DataTable rows={Object.entries(data.groups)} rowKey={([g]) => g} columns={[
            { key: 'g', header: 'Group', render: ([g]) => g }, { key: 'n', header: 'Candidates', align: 'right', render: ([, s]) => s.n },
            { key: 's', header: 'Selected', align: 'right', render: ([, s]) => s.selected }, { key: 'r', header: 'Selection rate (95% interval)', align: 'right', render: ([, s]) => <span>{num(s.rate, 2)} <span className="text-xs text-muted-foreground">({num(s.rate_ci_low, 2)} to {num(s.rate_ci_high, 2)}){s.small_group ? ' small group' : ''}</span></span> },
            { key: 'i', header: 'Impact ratio', align: 'right', render: ([, s]) => num(s.impact_ratio, 2) },
            { key: 'x', header: 'Result', render: ([, s]) => s.flagged ? <Badge color="destructive" dot>Under 0.8</Badge> : <Badge color="success" dot>OK</Badge> },
          ]} /></>}
        {kind === 'weat' && <p className="text-sm">{data.group_x} vs {data.group_y}: effect size <b className="tabular-nums">{num(data.effect_size, 3)}</b>, permutation p-value <b className="tabular-nums">{num(data.p_value, 3)}</b> ({data.permutations} permutations, model {data.embedder}). {data.interpretation}</p>}
        <p className="text-xs text-muted-foreground">{data.limits}</p>
      </div>
    </Card>
  )
}
