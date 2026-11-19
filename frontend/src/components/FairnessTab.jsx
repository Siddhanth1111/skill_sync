import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import TrendChart from './TrendChart.jsx'

const fmt = (v, d = 1) => (v == null ? '-' : Number(v).toFixed(d))

// Seeded so the same candidates always get the same synthetic labels.
const syntheticGroup = (id) => ((id * 2654435761) >>> 0) % 2 === 0 ? 'A' : 'B'

export default function FairnessTab({ job, onError }) {
  const [candidates, setCandidates] = useState([])
  const [history, setHistory] = useState([])
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState(null) // {kind, data}
  const [groups, setGroups] = useState({})
  const [topN, setTopN] = useState(3)
  const [weatGroups, setWeatGroups] = useState('gender')

  const loadHistory = useCallback(() => api.auditHistory(job.id).then(setHistory).catch((e) => onError(e.message)), [job.id]) // eslint-disable-line
  useEffect(() => {
    api.matrix(job.id).then((m) => {
      const sc = m.candidates.filter((c) => c.scored)
      setCandidates(sc)
      setGroups(Object.fromEntries(sc.map((c) => [c.id, syntheticGroup(c.id)])))
      setTopN(Math.max(1, Math.round(sc.length / 3)))
    }).catch((e) => onError(e.message))
    loadHistory()
  }, [job.id]) // eslint-disable-line

  const run = async (kind, fn) => {
    setBusy(kind); onError('')
    try { setResult({ kind, data: await fn() }); await loadHistory() } catch (e) { onError(e.message) } finally { setBusy('') }
  }

  if (!candidates.length) return <p className="muted">Run scoring first (Ranking tab). Audits compare against the stored scores.</p>

  const byKind = {}
  history.forEach((h) => { (byKind[h.kind] ||= []).push({ id: h.audit_id, value: h.headline?.value, label: h.headline?.label }) })

  return (
    <div>
      <div className="warning">
        Audits use synthetic group labels and simple text transformations. They do not cover proxies such as school, address or
        employment gaps, and a pass is not proof of fairness. Use flags to decide where a human should look.
      </div>

      <div className="audit-buttons">
        <div className="panel">
          <b>Blind mode</b>
          <p className="small">Removes name, contact details, links, postcode, school names and education years, makes pronouns neutral, and rescores.</p>
          <button className="primary" disabled={!!busy} onClick={() => run('blind', () => api.auditBlind(job.id))}>{busy === 'blind' ? 'Running...' : 'Run blind audit'}</button>
        </div>
        <div className="panel">
          <b>Counterfactual swap</b>
          <p className="small">Swaps names and pronouns for each candidate and flags any score change above 2 points (of 100).</p>
          <button className="primary" disabled={!!busy} onClick={() => run('counterfactual', () => api.auditCounterfactual(job.id))}>{busy === 'counterfactual' ? 'Running...' : 'Run counterfactual'}</button>
        </div>
        <div className="panel">
          <b>Adverse impact</b>
          <p className="small">Selection = in the top N. Ratio below 0.8 against the best-selected group is flagged.</p>
          <label className="small">Top N <input className="num" type="number" min="1" max={candidates.length} value={topN} onChange={(e) => setTopN(Number(e.target.value))} /></label>
          <button className="primary" disabled={!!busy} onClick={() => run('impact', () => api.auditImpact(job.id, groups, topN))}>{busy === 'impact' ? 'Running...' : 'Run impact ratio'}</button>
        </div>
        <div className="panel">
          <b>WEAT probe</b>
          <p className="small">Tests the embedding model for biased word associations between name groups.</p>
          <select value={weatGroups} onChange={(e) => setWeatGroups(e.target.value)}><option value="gender">gender-coded names</option><option value="origin">Anglo vs Indian names</option></select>
          <button className="primary" disabled={!!busy} onClick={() => run('weat', () => api.auditWeat(job.id, weatGroups))}>{busy === 'weat' ? 'Running...' : 'Run WEAT'}</button>
        </div>
      </div>

      <details>
        <summary>Synthetic group labels for the impact audit ({candidates.length} candidates)</summary>
        <table><thead><tr><th>Candidate</th><th>Group (synthetic)</th></tr></thead>
          <tbody>{candidates.map((c) => (
            <tr key={c.id}><td>{c.name || c.filename}</td>
              <td><input value={groups[c.id] || ''} onChange={(e) => setGroups({ ...groups, [c.id]: e.target.value })} /></td></tr>
          ))}</tbody>
        </table>
      </details>

      {result && <AuditResult kind={result.kind} data={result.data} />}

      <h2>Monitoring over time</h2>
      {history.length === 0 ? <p className="muted">No audits yet. Every run is saved and charted here.</p> : (
        <div className="trends">
          {Object.entries(byKind).map(([k, pts]) => <TrendChart key={k} label={`${k}: ${pts[0].label || ''}`} points={pts} />)}
        </div>
      )}
    </div>
  )
}

function AuditResult({ kind, data }) {
  return (
    <div className="panel">
      <h3>Result: {kind}</h3>
      {kind === 'blind' && (
        <>
          <p>Average change {fmt(data.avg_change, 2)} points (absolute {fmt(data.avg_abs_change, 2)}). <b>{data.rank_changes}</b> of {data.candidates.length} candidates changed rank.</p>
          <table><thead><tr><th>Candidate</th><th>Normal</th><th>Blind</th><th>Change</th><th>Rank</th></tr></thead>
            <tbody>{data.candidates.map((c) => (
              <tr key={c.candidate_id} className={c.rank_normal !== c.rank_blind ? 'flag' : ''}>
                <td>{c.name}</td><td>{fmt(c.normal)}</td><td>{fmt(c.blind)}</td><td>{fmt(c.change, 2)}</td><td>{c.rank_normal} → {c.rank_blind}</td></tr>
            ))}</tbody></table>
        </>
      )}
      {kind === 'counterfactual' && (
        <>
          <p><b>{data.flagged_count}</b> candidate(s) flagged (change above {data.threshold_points} points). Largest change {fmt(data.max_abs_change, 2)} points.</p>
          <table><thead><tr><th>Candidate</th><th>Male-name variant</th><th>Female-name variant</th><th>Flag</th></tr></thead>
            <tbody>{data.candidates.map((c) => (
              <tr key={c.candidate_id} className={c.flagged ? 'flag' : ''}>
                <td>{c.name}</td><td>{fmt(c.change_male_variant, 2)}</td><td>{fmt(c.change_female_variant, 2)}</td><td>{c.flagged ? 'FLAGGED' : 'ok'}</td></tr>
            ))}</tbody></table>
        </>
      )}
      {kind === 'impact' && (
        <>
          <p>Top {data.top_n} selected from {data.n_candidates}. Demographic parity difference (Fairlearn): <b>{fmt(data.demographic_parity_difference, 3)}</b>.
            {data.flagged_groups.length ? <> Flagged (ratio under {data.ratio_threshold}): <b>{data.flagged_groups.join(', ')}</b>.</> : ' No group flagged.'}</p>
          <table><thead><tr><th>Group</th><th>Candidates</th><th>Selected</th><th>Selection rate</th><th>Impact ratio</th></tr></thead>
            <tbody>{Object.entries(data.groups).map(([g, s]) => (
              <tr key={g} className={s.flagged ? 'flag' : ''}><td>{g}</td><td>{s.n}</td><td>{s.selected}</td><td>{fmt(s.rate, 2)}</td><td>{fmt(s.impact_ratio, 2)}</td></tr>
            ))}</tbody></table>
        </>
      )}
      {kind === 'weat' && (
        <p>{data.group_x} vs {data.group_y}: effect size <b>{fmt(data.effect_size, 3)}</b>, permutation p-value <b>{fmt(data.p_value, 3)}</b> ({data.permutations} permutations, model {data.embedder}). {data.interpretation}</p>
      )}
      <p className="small">{data.limits}</p>
    </div>
  )
}
