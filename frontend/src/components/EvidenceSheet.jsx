import { Fragment, useEffect, useState } from 'react'
import { Flag, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../api/index.js'
import { gaps, statusOf } from '../lib/rank.js'
import { Badge, ImportanceBadge, KindBadge, SourceBadge, StatusBadge, isScoredKind } from './ui/Badge.jsx'
import { Button } from './ui/Button.jsx'
import { Sheet } from './ui/Overlay.jsx'
import { Alert, Skeleton } from './ui/Feedback.jsx'
import { cn } from '../lib/utils.js'

const ORDER = { not_met: 0, not_verifiable: 1, partial: 2, met: 3 }
const EDGE = { met: 'border-l-success', partial: 'border-l-warning', not_met: 'border-l-destructive', not_verifiable: 'border-l-border' }

// The supporting sentence is highlighted inside the whole evidence unit (a bullet or sentence, never a page).
function Quote({ text, sentence }) {
  const flat = (s) => s.replace(/\s+/g, ' ')
  const i = sentence ? flat(text).indexOf(flat(sentence)) : -1
  if (i < 0 || flat(sentence) === flat(text)) return <p className="whitespace-pre-wrap text-xs leading-relaxed">{sentence && flat(sentence) === flat(text) ? <mark className="rounded-sm bg-accent px-0.5 text-foreground">{text}</mark> : text}</p>
  const f = flat(text)
  return <p className="whitespace-pre-wrap text-xs leading-relaxed">{f.slice(0, i)}<mark className="rounded-sm bg-accent px-0.5 text-foreground">{f.slice(i, i + flat(sentence).length)}</mark>{f.slice(i + flat(sentence).length)}</p>
}

const SKILL_NOTE = { evidence: 'shown in the work history', listed: 'only listed under skills', related_only: 'a related tool was found, not this one', technique_only: 'a specific method of this skill was found (partial credit)', not_found: 'not found in the evidence' }

function Trace({ trace }) {
  if (!trace) return null
  const kept = trace.retrieved || []
  return (
    <details className="mt-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none hover:text-foreground">How this was scored</summary>
      <dl className="mt-1.5 grid grid-cols-[7rem_1fr] gap-x-2 gap-y-1">
        <dt>Searched as</dt><dd>"{trace.query}" ({trace.kind}{trace.mode === 'any' ? ', any one of the skills' : ''})</dd>
        <dt>Rule</dt><dd>{({ skill_evidence: 'skill found in evidence', rerank_only: 'reranker only (no known skill)', years: 'years with the skill against years required', education: 'degree level and field of study' })[trace.rule] || trace.rule}</dd>
        {trace.skills && Object.entries(trace.skills).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{SKILL_NOTE[v] || v}</dd></Fragment>)}
        {trace.years_required != null && <><dt>Years</dt><dd>{trace.years_used ?? trace.years_total} found, {trace.years_required} required{trace.note ? `. ${trace.note}` : ''}</dd></>}
        {trace.field_mismatch && <><dt>Field of study</dt><dd>did not match {trace.field_mismatch.join(', ')}; score reduced</dd></>}
        {trace.equivalence_rule && <><dt>Equivalence</dt><dd>{trace.equivalence_rule}</dd></>}
        {trace.weak_evidence_cap && <><dt>Capped</dt><dd>weak evidence cannot make a requirement met</dd></>}
        <dt>Candidates</dt><dd>{kept.length} passages retrieved, best reranker score {kept.length ? Math.max(...kept.map((k) => k.rerank)).toFixed(2) : '-'}</dd>
        <dt>Pipeline</dt><dd>{trace.version}</dd>
      </dl>
    </details>
  )
}

// Stage 12 in the UI: every scored requirement with its score, status, supporting sentence and section (unmet
// first), the biggest gaps, the narrative, and the requirements that are listed but not scored. Statuses and gaps
// follow the current slider weights; quotes are from the stored matrix.
export default function EvidenceSheet({ candidate, requirements, thresholds, finalScore, rankRow, hubMax = 3, rating, onRate, onClose }) {
  const [explain, setExplain] = useState(null)
  const [narrativeError, setNarrativeError] = useState('')
  const [verdicts, setVerdicts] = useState({})

  // A verdict on the evidence (the wrong-evidence button) is saved for the reviewer; sending another replaces it.
  const flag = async (requirementId, judgement) => {
    const prev = verdicts[requirementId]
    if (prev?.judgement === judgement) return
    setVerdicts((v) => ({ ...v, [requirementId]: { judgement } }))
    try { await api.flagEvidence(candidate.id, requirementId, judgement, judgement === 'correct' ? 2 : judgement === 'wrong_evidence' ? 0 : undefined) }
    catch { setVerdicts((v) => ({ ...v, [requirementId]: prev })) }
  }

  useEffect(() => {
    if (!candidate) return
    setExplain(null); setNarrativeError(''); setVerdicts({})
    api.explanation(candidate.id).then(setExplain).catch((e) => setNarrativeError(e.message))
    api.evidenceFeedback(candidate.id).then(setVerdicts).catch(() => {})
  }, [candidate?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!candidate) return null
  const narrative = explain?.narrative
  const traces = Object.fromEntries((explain?.requirements || []).map((r) => [r.id, r.trace]))
  const scores = Object.fromEntries(Object.entries(candidate.scores).map(([id, s]) => [Number(id), s.score]))
  const rows = requirements.filter((r) => candidate.scores[r.id])
    .map((r) => ({ ...r, ...candidate.scores[r.id], status: candidate.scores[r.id].unverifiable ? 'not_verifiable' : statusOf(candidate.scores[r.id].score, thresholds) }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.weight - a.weight)
  const byId = Object.fromEntries(requirements.map((r) => [r.id, r]))
  const gapList = gaps(requirements, scores).slice(0, 5)
  const listed = requirements.filter((r) => !isScoredKind(r.meta?.kind))

  return (
    <Sheet open onClose={onClose} title={candidate.name || candidate.filename} subtitle={candidate.name ? candidate.filename : undefined}>
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div><p className="text-xs text-muted-foreground">Score with current weights</p>
            <p className="text-2xl font-medium tabular-nums leading-tight">{(finalScore * 100).toFixed(0)}<span className="text-sm font-normal text-muted-foreground"> / 100</span></p>
            {rankRow && <p className="text-xs text-muted-foreground">Tier {rankRow.tier}{rankRow.tied ? ' (too close to separate from others in it)' : ''} · must-haves met: {rankRow.musts_met} of {rankRow.musts}</p>}</div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground">Rate this candidate</span>
            <Button variant="outline" iconOnly selected={rating === 'up'} aria-label="Good fit" aria-pressed={rating === 'up'} onClick={() => onRate('up')}><ThumbsUp /></Button>
            <Button variant="outline" iconOnly selected={rating === 'down'} aria-label="Not a fit" aria-pressed={rating === 'down'} onClick={() => onRate('down')}><ThumbsDown /></Button>
          </div>
        </div>
        <p className="-mt-2 text-xs text-muted-foreground">A person makes every hiring decision. Scores are evidence for a reviewer, not a verdict. Quotations come from the resume with names, contact details, schools and pronouns removed, which is the text the scorer saw.</p>

        <section>
          <div className="mb-1 flex items-center gap-2"><h3 className="text-sm font-medium">Summary</h3>{narrative && <SourceBadge source={narrative.source === 'llm' ? 'llm' : 'rules'} label={narrative.source === 'llm' ? 'Language model' : 'Template'} />}</div>
          {narrative ? <p className="text-sm leading-relaxed">{narrative.text}</p>
            : narrativeError ? <Alert color="destructive">{narrativeError}</Alert>
            : <div className="flex flex-col gap-2"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-4/5" /></div>}
          {narrative?.source === 'template' && <p className="mt-1 text-xs text-muted-foreground">Template summary. It is used when the language model is unavailable or when a quotation in its text cannot be verified.</p>}
        </section>

        <section>
          <h3 className="mb-1 text-sm font-medium">Biggest gaps</h3>
          {gapList.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {gapList.map((g) => <li key={g.requirement_id} className="flex gap-2"><span className="w-14 shrink-0 tabular-nums text-primary">+{g.points_gain.toFixed(1)}</span><span>{byId[g.requirement_id].text}</span></li>)}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No gaps. Every requirement scores 100.</p>}
        </section>

        <section>
          <h3 className="mb-2 text-sm font-medium">Requirements <span className="font-normal text-muted-foreground">(unmet first)</span></h3>
          <div className="flex flex-col gap-2">
            {rows.map((r) => (
              <article key={r.id} className={cn('rounded-md border border-border border-l-4 p-3', EDGE[r.status])}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={r.status} /><ImportanceBadge importance={r.importance} /><KindBadge kind={r.meta?.kind} />
                  <span className="ml-auto text-xs tabular-nums text-muted-foreground">score {(r.score * 100).toFixed(0)} · weight {r.weight}</span>
                </div>
                <p className="mt-1.5 text-sm">{r.text}</p>
                {r.status === 'not_verifiable' && <Alert color="warning" className="mt-2">The resume was read poorly (scan quality or little text), so a missing match cannot be trusted. It is not counted against the candidate.</Alert>}
                {r.quote ? (
                  <blockquote className="mt-2 rounded-sm border-l-2 border-border bg-muted/40 px-3 py-2">
                    <Quote text={r.quote} sentence={r.sentence} />
                    <p className="mt-1 text-xs text-muted-foreground">From the {r.section} section · verified in the resume text{r.entailment != null && ` · entailment ${r.entailment.toFixed(2)}`}</p>
                    {r.weak && <Alert color="warning" className="mt-2">Weak evidence: the passage may not support this requirement, so it cannot count as met. Read it before relying on the score.</Alert>}
                    {r.hub && <Alert color="warning" className="mt-2">The same passage is the evidence for more than {hubMax} requirements. It may be a generic line; check that it really supports this one.</Alert>}
                  </blockquote>
                ) : <p className="mt-2 text-xs text-muted-foreground">No verified quotation for this requirement.</p>}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Is this evidence right?</span>
                  <Button variant="outline" size="sm" selected={verdicts[r.id]?.judgement === 'correct'} aria-pressed={verdicts[r.id]?.judgement === 'correct'} onClick={() => flag(r.id, 'correct')}>Yes</Button>
                  <Button variant="outline" size="sm" leftIcon={<Flag />} selected={verdicts[r.id]?.judgement === 'wrong_evidence'} aria-pressed={verdicts[r.id]?.judgement === 'wrong_evidence'} onClick={() => flag(r.id, 'wrong_evidence')}>Wrong evidence</Button>
                  <Button variant="outline" size="sm" selected={verdicts[r.id]?.judgement === 'missed_evidence'} aria-pressed={verdicts[r.id]?.judgement === 'missed_evidence'} onClick={() => flag(r.id, 'missed_evidence')}>It is elsewhere in the resume</Button>
                </div>
                <Trace trace={traces[r.id]} />
              </article>
            ))}
          </div>
        </section>

        {listed.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-medium">Listed, not scored <span className="font-normal text-muted-foreground">({listed.length})</span></h3>
            <p className="mb-1 text-xs text-muted-foreground">Soft skills and duties cannot be verified from a resume. Raise them in the interview.</p>
            <ul className="flex flex-col gap-1 text-sm">{listed.map((r) => <li key={r.id} className="flex items-center gap-2"><KindBadge kind={r.meta?.kind} /><span>{r.text}</span></li>)}</ul>
          </section>
        )}
      </div>
    </Sheet>
  )
}
