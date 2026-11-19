import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { gaps, statusOf } from '../lib/rank.js'

const ORDER = { not_met: 0, partial: 1, met: 2 }
const LABEL = { met: 'met', partial: 'partial', not_met: 'not met' }

// Stage 12: every requirement with score, status, quotation and section (unmet first), gaps by points gained,
// and the narrative. Statuses and gaps follow the current slider weights; quotes come from the stored matrix.
export default function EvidenceDrawer({ candidate, requirements, thresholds, finalScore, rating, onRate, onClose }) {
  const [narrative, setNarrative] = useState(null)
  const [narrativeError, setNarrativeError] = useState('')

  useEffect(() => {
    setNarrative(null); setNarrativeError('')
    api.explanation(candidate.id).then((e) => setNarrative(e.narrative)).catch((e) => setNarrativeError(e.message))
  }, [candidate.id])

  const scores = Object.fromEntries(Object.entries(candidate.scores).map(([id, s]) => [Number(id), s.score]))
  const rows = requirements
    .filter((r) => candidate.scores[r.id])
    .map((r) => ({ ...r, ...candidate.scores[r.id], status: statusOf(candidate.scores[r.id].score, thresholds) }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.weight - a.weight)
  const gapList = gaps(requirements, scores).slice(0, 5)
  const byId = Object.fromEntries(requirements.map((r) => [r.id, r]))

  return (
    <div className="drawer">
      <button className="close" onClick={onClose}>close</button>
      <h3>{candidate.name || candidate.filename}</h3>
      <div className="row">
        <span className="bigscore">{(finalScore * 100).toFixed(0)}</span><span className="small">/ 100 with current weights</span>
        <span className="spacer" />
        <button className={rating === 'up' ? 'rate on' : 'rate'} onClick={() => onRate('up')} title="Good fit">👍</button>
        <button className={rating === 'down' ? 'rate on' : 'rate'} onClick={() => onRate('down')} title="Not a fit">👎</button>
      </div>
      <p className="small">A person makes every hiring decision. These scores are evidence, not a verdict.</p>

      <h4>Summary {narrative && <span className={'tag ' + (narrative.source === 'llm' ? 'llm' : 'rules')}>{narrative.source}</span>}</h4>
      {narrative ? <p>{narrative.text}</p> : narrativeError ? <p className="error">{narrativeError}</p> : <p className="muted">Writing summary...</p>}
      {narrative?.source === 'template' && <p className="small">Template summary (the language model was unavailable, or a quotation could not be verified).</p>}

      <h4>Biggest gaps</h4>
      {gapList.length ? (
        <ul className="gaps">
          {gapList.map((g) => <li key={g.requirement_id}><b>+{g.points_gain.toFixed(1)}</b> points: {byId[g.requirement_id].text}</li>)}
        </ul>
      ) : <p className="muted">No gaps.</p>}

      <h4>Requirements</h4>
      {rows.map((r) => (
        <div key={r.id} className={'req ' + r.status}>
          <div className="row">
            <span className={'tag ' + (r.status === 'met' ? 'met' : r.status === 'partial' ? 'should' : 'must')}>{LABEL[r.status]}</span>
            <span className={'tag ' + r.importance}>{r.importance}</span>
            <span className="small">score {(r.score * 100).toFixed(0)} · weight {r.weight}</span>
          </div>
          <div>{r.text}</div>
          {r.quote ? (
            <blockquote>
              {r.quote}
              <div className="small">from the {r.section} section{r.entailment != null && ` · entailment ${r.entailment.toFixed(2)}`}</div>
              {r.weak && <div className="warning">Weak evidence: the quotation may not support this requirement. Read it before relying on the score.</div>}
            </blockquote>
          ) : <div className="small muted">No verified quotation.</div>}
        </div>
      ))}
    </div>
  )
}
