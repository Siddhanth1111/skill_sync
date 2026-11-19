import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const NAMES = {
  overall_score: 'overall score', mean_must: 'mean on musts', mean_should: 'mean on shoulds', mean_nice: 'mean on nices',
  share_met: 'share met', share_partial: 'share partial', share_not_met: 'share not met',
}

// Stage 13: ratings -> optional learned score, shown beside the rule-based score and never replacing it.
export default function LearningTab({ job, onError }) {
  const [model, setModel] = useState(null)
  const [ranking, setRanking] = useState([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [m, r] = await Promise.all([api.model(job.id), api.ranking(job.id)])
    setModel(m); setRanking(r.ranking)
  }, [job.id])
  useEffect(() => { load().catch((e) => onError(e.message)) }, [load]) // eslint-disable-line

  const train = async () => {
    setBusy(true); onError('')
    try { setModel(await api.trainModel(job.id)); setRanking((await api.ranking(job.id)).ranking) } catch (e) { onError(e.message) } finally { setBusy(false) }
  }

  if (!model) return <p className="muted">Loading...</p>
  const m = model.metrics
  return (
    <div>
      <p>Rate candidates with 👍 or 👎 in the evidence drawer (Ranking tab). Once there are at least {model.min_ratings} ratings with at
        least {model.min_each} of each kind, a logistic regression can be trained on seven requirement-level features.</p>
      <div className="row">
        <span className="tag met">👍 {model.up}</span><span className="tag must">👎 {model.down}</span>
        <button className="primary" disabled={!model.can_train || busy} onClick={train}>{busy ? 'Training...' : model.trained ? 'Retrain' : 'Train learned score'}</button>
        {!model.can_train && <span className="small">Not enough ratings yet.</span>}
      </div>

      {m && (
        <div className="panel">
          <h3>Cross-validated quality ({m.cv_folds}-fold, {m.n} ratings)</h3>
          <table><tbody>
            <tr><td>AUC</td><td><b>{m.cv_auc.toFixed(3)}</b></td><td className="small">0.5 means no signal, 1.0 means perfect</td></tr>
            <tr><td>Brier score</td><td><b>{m.brier.toFixed(3)}</b></td><td className="small">lower is better</td></tr>
            <tr><td>Expected calibration error</td><td><b>{m.ece.toFixed(3)}</b></td><td className="small">0 means probabilities match outcomes</td></tr>
          </tbody></table>
          <p className="small">{model.note}</p>
        </div>
      )}

      {model.trained && (
        <table>
          <thead><tr><th>Candidate</th><th>Rule score</th><th>Learned (likelihood of 👍)</th><th>What drives it (SHAP, log-odds)</th></tr></thead>
          <tbody>{ranking.map((r) => {
            const l = model.learned[r.candidate_id]
            const top = l ? Object.entries(l.shap).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3) : []
            return (
              <tr key={r.candidate_id}>
                <td>{r.name || r.filename}</td><td>{(r.final_score * 100).toFixed(1)}</td>
                <td>{l ? `${(l.probability * 100).toFixed(0)}%` : '-'}</td>
                <td className="small">{top.map(([k, v]) => `${NAMES[k]} ${v >= 0 ? '+' : ''}${v.toFixed(2)}`).join(' · ')}</td>
              </tr>
            )
          })}</tbody>
        </table>
      )}
    </div>
  )
}
