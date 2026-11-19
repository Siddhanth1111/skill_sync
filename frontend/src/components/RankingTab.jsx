import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../usePolling.js'
import { rankCandidates } from '../lib/rank.js'
import EvidenceDrawer from './EvidenceDrawer.jsx'

// Stages 7 to 11 in the UI. Scores come from the server once (the matrix); after that, moving a slider or
// changing an importance re-ranks right here with the same formula as the backend, with no server call.
export default function RankingTab({ job, onJobChange, onError }) {
  const [matrix, setMatrix] = useState(null)
  const [run, setRun] = useState(null)
  const [reqs, setReqs] = useState([]) // local, editable copy: importance and weight
  const [serverRank, setServerRank] = useState({}) // candidate id -> {rating, learned_probability}
  const [selected, setSelected] = useState(null)
  const [minScore, setMinScore] = useState(0)

  const loadMatrix = useCallback(async () => {
    const [m, r] = await Promise.all([api.matrix(job.id), api.ranking(job.id)])
    setMatrix(m); setReqs(m.requirements.map((x) => ({ ...x })))
    setServerRank(Object.fromEntries(r.ranking.map((x) => [x.candidate_id, x])))
  }, [job.id])

  const loadRun = useCallback(() => api.scoringStatus(job.id).then(setRun), [job.id])

  useEffect(() => {
    setSelected(null)
    loadMatrix().catch((e) => onError(e.message))
    loadRun().catch((e) => onError(e.message))
  }, [loadMatrix, loadRun]) // eslint-disable-line

  const running = run?.status === 'running'
  usePolling(async () => {
    const r = await api.scoringStatus(job.id)
    setRun(r)
    if (r.status !== 'running') await loadMatrix()
  }, running, 1200)

  const start = async () => {
    try { setRun(await api.startScoring(job.id)) } catch (e) { onError(e.message) }
  }

  const scored = useMemo(() => (matrix ? matrix.candidates.filter((c) => c.scored) : []), [matrix])
  const ranked = useMemo(() => {
    if (!matrix) return []
    const m = Object.fromEntries(scored.map((c) => [c.id, Object.fromEntries(Object.entries(c.scores).map(([k, v]) => [k, v.score]))]))
    return rankCandidates(reqs, m, matrix.thresholds)
  }, [matrix, scored, reqs])

  const byId = useMemo(() => Object.fromEntries((matrix?.candidates || []).map((c) => [c.id, c])), [matrix])
  const edit = (id, field, value) => setReqs((rs) => rs.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  const dirty = matrix && reqs.some((r, i) => r.importance !== matrix.requirements[i].importance || Number(r.weight) !== Number(matrix.requirements[i].weight))

  const saveWeights = async () => {
    try {
      onJobChange(await api.patchRequirements(job.id, reqs.map((r) => ({ id: r.id, importance: r.importance, weight: Number(r.weight) }))))
      await loadMatrix()
    } catch (e) { onError(e.message) }
  }

  const rate = async (rating) => {
    try {
      await api.rate(selected, rating)
      setServerRank((s) => ({ ...s, [selected]: { ...s[selected], rating } }))
    } catch (e) { onError(e.message) }
  }

  const unscoredCount = matrix ? matrix.candidates.length - scored.length : 0
  const shown = ranked.filter((r) => r.final_score * 100 >= minScore)
  const sel = selected != null ? byId[selected] : null

  return (
    <div>
      <div className="row">
        <button className="primary" onClick={start} disabled={running}>{run?.status === 'done' || scored.length ? 'Re-run scoring' : 'Run scoring'}</button>
        {running && <span>Scoring {run.done} of {run.total} resumes...</span>}
        {run?.status === 'failed' && <span className="error">Scoring failed: {run.error}</span>}
        {run?.config && <span className="small">models: {run.config.embedder} · {run.config.reranker} · {run.config.nli}</span>}
      </div>
      {matrix?.stale && <div className="warning">Requirement wording changed since the last run. Re-run scoring to refresh the evidence.</div>}
      {unscoredCount > 0 && !running && <div className="warning">{unscoredCount} parsed resume(s) have not been scored yet.</div>}
      {matrix && matrix.candidates.length === 0 && <p className="muted">No parsed resumes yet. Upload resumes in the Requirements and resumes tab.</p>}

      {scored.length > 0 && (
        <div className="rank-grid">
          <div className="weights">
            <h4>Weights <span className="small">(live re-rank, no server call)</span></h4>
            {reqs.map((r) => (
              <div key={r.id} className="wrow">
                <div className="small">{r.text}</div>
                <div className="row">
                  <select value={r.importance} onChange={(e) => edit(r.id, 'importance', e.target.value)}>
                    <option value="must">must</option><option value="should">should</option><option value="nice">nice</option>
                  </select>
                  <input type="range" min="0" max="5" step="0.5" value={r.weight} onChange={(e) => edit(r.id, 'weight', Number(e.target.value))} />
                  <span className="wnum">{r.weight}</span>
                </div>
              </div>
            ))}
            <div className="row">
              <button className="primary" disabled={!dirty} onClick={saveWeights}>Save as default</button>
              <button disabled={!dirty} onClick={() => setReqs(matrix.requirements.map((x) => ({ ...x })))}>Reset</button>
            </div>
            <label className="small">Show candidates scoring at least {minScore}
              <input type="range" min="0" max="100" step="5" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
            </label>
          </div>

          <div>
            <table>
              <thead><tr><th>#</th><th>Candidate</th><th style={{ width: 200 }}>Score</th><th>Met</th><th>Partial</th><th>Missing</th><th>Musts met</th><th>Learned</th><th /></tr></thead>
              <tbody>
                {shown.map((r) => {
                  const c = byId[r.candidate_id]
                  const sr = serverRank[r.candidate_id] || {}
                  return (
                    <tr key={r.candidate_id} className={r.candidate_id === selected ? 'sel' : ''} onClick={() => setSelected(r.candidate_id)}>
                      <td>{r.rank}</td>
                      <td>{c.name || c.filename}<div className="small">{c.filename}</div></td>
                      <td><div className="bar"><div style={{ width: `${r.final_score * 100}%` }} /></div><span className="small">{(r.final_score * 100).toFixed(1)}</span></td>
                      <td>{r.met}</td><td>{r.partial}</td><td>{r.not_met}</td>
                      <td>{r.musts_met}</td>
                      <td className="small">{sr.learned_probability != null ? `${(sr.learned_probability * 100).toFixed(0)}%` : '-'}</td>
                      <td>{sr.rating === 'up' ? '👍' : sr.rating === 'down' ? '👎' : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {shown.length === 0 && <p className="muted">No candidates at this threshold.</p>}
          </div>
        </div>
      )}

      {sel && sel.scored && (
        <EvidenceDrawer
          candidate={sel} requirements={reqs} thresholds={matrix.thresholds}
          finalScore={ranked.find((r) => r.candidate_id === sel.id)?.final_score ?? 0}
          rating={serverRank[sel.id]?.rating} onRate={rate} onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
