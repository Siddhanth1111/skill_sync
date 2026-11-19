import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../usePolling.js'
import RequirementsTable from '../components/RequirementsTable.jsx'
import CandidateView from '../components/CandidateView.jsx'
import FileDrop from '../components/FileDrop.jsx'

const PHASES = { start_here: 'Start here (must-haves)', next: 'Next (should-haves)', later: 'Later (nice-to-haves)' }

export default function Student() {
  const [candidate, setCandidate] = useState(null)
  const [jds, setJds] = useState([])
  const [picked, setPicked] = useState({})
  const [matches, setMatches] = useState(null)
  const [openJob, setOpenJob] = useState(null)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { api.listJobs('student').then((j) => { setJds(j); setPicked(Object.fromEntries(j.map((x) => [x.id, true]))) }).catch((e) => setError(e.message)) }, [])

  const refresh = useCallback(() => (candidate ? api.getCandidate(candidate.id).then(setCandidate) : Promise.resolve()), [candidate?.id]) // eslint-disable-line
  usePolling(refresh, !!candidate && (candidate.status === 'queued' || candidate.status === 'parsing'))

  const upload = async (files) => {
    setError(''); setCandidate(null); setMatches(null); setOpenJob(null)
    try { setCandidate(await api.uploadStudentResume(files[0])) } catch (e) { setError(e.message) }
  }

  const addJd = async (e) => {
    e.preventDefault()
    setBusy('jd'); setError('')
    try {
      const j = await api.createJob(title || 'Untitled job', text, 'student')
      setJds((x) => [j, ...x]); setPicked((p) => ({ ...p, [j.id]: true })); setTitle(''); setText(''); setMatches(null)
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  const match = async () => {
    setBusy('match'); setError(''); setOpenJob(null)
    try { setMatches(await api.studentMatch(candidate.id, jds.filter((j) => picked[j.id]).map((j) => j.id))) } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const ready = candidate?.status === 'done'
  const chosen = jds.filter((j) => picked[j.id])

  return (
    <div>
      {error && <div className="error">{error}</div>}
      <div className="two-col">
        <section>
          <h2>1. Your resume</h2>
          <FileDrop multiple={false} onFiles={upload} label="Drop one PDF or DOCX resume here, or click to choose" />
          {candidate && <div className="panel"><CandidateView candidate={candidate} /></div>}
        </section>

        <section>
          <h2>2. Job descriptions</h2>
          <form onSubmit={addJd}>
            <input placeholder="Job title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
            <textarea rows={7} placeholder="Paste a job description" value={text} onChange={(e) => setText(e.target.value)} required minLength={20} />
            <button className="primary" disabled={busy === 'jd'}>{busy === 'jd' ? 'Extracting...' : 'Add job description'}</button>
          </form>
          {jds.map((j) => (
            <details key={j.id} className="panel">
              <summary>
                <label onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={!!picked[j.id]} onChange={(e) => setPicked({ ...picked, [j.id]: e.target.checked })} />
                </label>{' '}
                <b>{j.title}</b> <span className={'tag ' + (j.requirements_source === 'llm' ? 'llm' : 'rules')}>by {j.requirements_source}</span>
                <span className="small"> {j.requirements.length} requirements</span>
              </summary>
              <RequirementsTable requirements={j.requirements} />
            </details>
          ))}
        </section>
      </div>

      <h2>3. Match</h2>
      <button className="primary" disabled={!ready || chosen.length === 0 || busy === 'match'} onClick={match}>
        {busy === 'match' ? 'Scoring...' : `Match my resume to ${chosen.length} job(s)`}
      </button>
      {!ready && <span className="small"> Upload a resume and wait for it to finish parsing.</span>}

      {matches && (
        <div className="two-col">
          <div>
            <table>
              <thead><tr><th>#</th><th>Job</th><th style={{ width: 180 }}>Match</th><th>Met</th><th>Partial</th><th>Missing</th><th>Musts</th></tr></thead>
              <tbody>{matches.map((m, i) => (
                <tr key={m.job_id} className={m.job_id === openJob ? 'sel' : ''} onClick={() => setOpenJob(m.job_id)}>
                  <td>{i + 1}</td><td>{m.title}</td>
                  <td><div className="bar"><div style={{ width: `${m.final_score * 100}%` }} /></div><span className="small">{(m.final_score * 100).toFixed(1)}</span></td>
                  <td>{m.met}</td><td>{m.partial}</td><td>{m.not_met}</td><td>{m.musts_met}/{m.musts}</td>
                </tr>
              ))}</tbody>
            </table>
            <p className="small">Click a job to see your roadmap.</p>
          </div>
          {openJob && <Roadmap key={openJob} candidateId={candidate.id} jobId={openJob} onError={setError} />}
        </div>
      )}
    </div>
  )
}

function Roadmap({ candidateId, jobId, onError }) {
  const [rm, setRm] = useState(null)
  const [addition, setAddition] = useState('')
  const [sim, setSim] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.studentRoadmap(candidateId, jobId).then(setRm).catch((e) => onError(e.message)) }, [candidateId, jobId]) // eslint-disable-line
  const simulate = async (e) => {
    e.preventDefault(); setBusy(true); onError('')
    try { setSim(await api.studentWhatIf(candidateId, jobId, addition)) } catch (err) { onError(err.message) } finally { setBusy(false) }
  }

  if (!rm) return <p className="muted">Loading roadmap...</p>
  return (
    <div className="panel">
      <h3>Roadmap: {rm.title}</h3>
      <p>Now <b>{(rm.current_score * 100).toFixed(0)}</b>. If you close every gap: <b>{(rm.final_projected_score * 100).toFixed(0)}</b>.</p>
      {rm.steps.length === 0 && <p className="muted">Every requirement is already met.</p>}
      {Object.entries(PHASES).map(([phase, label]) => {
        const steps = rm.steps.filter((s) => s.phase === phase)
        return steps.length ? (
          <div key={phase}>
            <h4>{label}</h4>
            {steps.map((s) => (
              <div key={s.requirement_id} className="req">
                <div className="row"><b>{s.text}</b></div>
                <div className="row small">
                  <span className="tag partial-tag">{s.status.replace('_', ' ')}</span>
                  <span>+{s.points_gain.toFixed(1)} points</span><span>projected score {(s.projected_score * 100).toFixed(0)}</span>
                </div>
                <div>{s.action} <span className={'tag ' + (s.action_source === 'llm' ? 'llm' : 'rules')}>{s.action_source}</span></div>
              </div>
            ))}
          </div>
        ) : null
      })}

      <h4>What if...?</h4>
      <form onSubmit={simulate}>
        <textarea rows={3} value={addition} onChange={(e) => setAddition(e.target.value)} required minLength={5}
          placeholder="Describe a project or skill you could add, e.g. Built a Tableau dashboard analysing 5 years of sales data" />
        <button className="primary" disabled={busy}>{busy ? 'Scoring...' : 'Simulate'}</button>
      </form>
      {sim && (
        <div className="req">
          <p>Score {(sim.before * 100).toFixed(1)} → <b>{(sim.after * 100).toFixed(1)}</b> ({sim.delta_points >= 0 ? '+' : ''}{sim.delta_points.toFixed(1)} points). <span className="small">Nothing was saved.</span></p>
          {sim.changes.map((c) => <div key={c.requirement_id} className="small">{c.text}: {(c.before * 100).toFixed(0)} → {(c.after * 100).toFixed(0)}</div>)}
          {sim.changes.length === 0 && <div className="small muted">No requirement changed.</div>}
        </div>
      )}
    </div>
  )
}
