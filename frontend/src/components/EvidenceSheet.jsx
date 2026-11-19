import { useEffect, useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../api/index.js'
import { gaps, statusOf } from '../lib/rank.js'
import { Badge, ImportanceBadge, SourceBadge, StatusBadge } from './ui/Badge.jsx'
import { Button } from './ui/Button.jsx'
import { Sheet } from './ui/Overlay.jsx'
import { Alert, Skeleton } from './ui/Feedback.jsx'
import { cn } from '../lib/utils.js'

const ORDER = { not_met: 0, partial: 1, met: 2 }
const EDGE = { met: 'border-l-success', partial: 'border-l-warning', not_met: 'border-l-destructive' }

// Stage 12 in the UI: every requirement with its score, status, verified quotation and section (unmet first), the
// biggest gaps, and the narrative. Statuses and gaps follow the current slider weights; quotes are from the stored matrix.
export default function EvidenceSheet({ candidate, requirements, thresholds, finalScore, rating, onRate, onClose }) {
  const [narrative, setNarrative] = useState(null)
  const [narrativeError, setNarrativeError] = useState('')

  useEffect(() => {
    if (!candidate) return
    setNarrative(null); setNarrativeError('')
    api.explanation(candidate.id).then((e) => setNarrative(e.narrative)).catch((e) => setNarrativeError(e.message))
  }, [candidate?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!candidate) return null
  const scores = Object.fromEntries(Object.entries(candidate.scores).map(([id, s]) => [Number(id), s.score]))
  const rows = requirements.filter((r) => candidate.scores[r.id])
    .map((r) => ({ ...r, ...candidate.scores[r.id], status: statusOf(candidate.scores[r.id].score, thresholds) }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.weight - a.weight)
  const byId = Object.fromEntries(requirements.map((r) => [r.id, r]))
  const gapList = gaps(requirements, scores).slice(0, 5)

  return (
    <Sheet open onClose={onClose} title={candidate.name || candidate.filename} subtitle={candidate.name ? candidate.filename : undefined}>
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div><p className="text-xs text-muted-foreground">Score with current weights</p>
            <p className="text-2xl font-medium tabular-nums leading-tight">{(finalScore * 100).toFixed(0)}<span className="text-sm font-normal text-muted-foreground"> / 100</span></p></div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground">Rate this candidate</span>
            <Button variant="outline" iconOnly selected={rating === 'up'} aria-label="Good fit" aria-pressed={rating === 'up'} onClick={() => onRate('up')}><ThumbsUp /></Button>
            <Button variant="outline" iconOnly selected={rating === 'down'} aria-label="Not a fit" aria-pressed={rating === 'down'} onClick={() => onRate('down')}><ThumbsDown /></Button>
          </div>
        </div>
        <p className="-mt-2 text-xs text-muted-foreground">A person makes every hiring decision. Scores are evidence for a reviewer, not a verdict.</p>

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
                  <StatusBadge status={r.status} /><ImportanceBadge importance={r.importance} />
                  <span className="ml-auto text-xs tabular-nums text-muted-foreground">score {(r.score * 100).toFixed(0)} · weight {r.weight}</span>
                </div>
                <p className="mt-1.5 text-sm">{r.text}</p>
                {r.quote ? (
                  <blockquote className="mt-2 rounded-sm border-l-2 border-border bg-muted/40 px-3 py-2">
                    <p className="whitespace-pre-wrap text-xs leading-relaxed">{r.quote}</p>
                    <p className="mt-1 text-xs text-muted-foreground">From the {r.section} section · verified in the resume{r.entailment != null && ` · entailment ${r.entailment.toFixed(2)}`}</p>
                    {r.weak && <Alert color="warning" className="mt-2">Weak evidence: the quotation may not support this requirement. Read it before relying on the score.</Alert>}
                  </blockquote>
                ) : <p className="mt-2 text-xs text-muted-foreground">No verified quotation for this requirement.</p>}
              </article>
            ))}
          </div>
        </section>
      </div>
    </Sheet>
  )
}
