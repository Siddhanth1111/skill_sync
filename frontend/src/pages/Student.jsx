import { useCallback, useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../usePolling.js'
import RequirementsTable from '../components/RequirementsTable.jsx'
import CandidateView from '../components/CandidateView.jsx'
import FileDrop from '../components/FileDrop.jsx'

export default function Student() {
  const [candidate, setCandidate] = useState(null)
  const [jds, setJds] = useState([]) // jobs created from pasted descriptions
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(
    () => (candidate ? api.getCandidate(candidate.id).then(setCandidate) : Promise.resolve()),
    [candidate?.id], // eslint-disable-line react-hooks/exhaustive-deps
  )
  usePolling(refresh, !!candidate && (candidate.status === 'queued' || candidate.status === 'parsing'))

  const upload = async (files) => {
    setError(''); setCandidate(null)
    try { setCandidate(await api.uploadStudentResume(files[0])) } catch (e) { setError(e.message) }
  }

  const addJd = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const j = await api.createJob(title || 'Untitled job', text)
      setJds((x) => [j, ...x]); setTitle(''); setText('')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="two-col">
      {error && <div className="error wide">{error}</div>}
      <section>
        <h2>Your resume</h2>
        <FileDrop multiple={false} onFiles={upload} label="Drop one PDF or DOCX resume here, or click to choose" />
        {candidate && <div className="panel"><CandidateView candidate={candidate} /></div>}
      </section>

      <section>
        <h2>Job descriptions</h2>
        <form onSubmit={addJd}>
          <input placeholder="Job title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea rows={8} placeholder="Paste a job description" value={text}
            onChange={(e) => setText(e.target.value)} required minLength={20} />
          <button className="primary" disabled={busy}>{busy ? 'Extracting...' : 'Add job description'}</button>
        </form>
        {jds.map((j) => (
          <div key={j.id} className="panel">
            <h3>{j.title} <span className={'tag ' + (j.requirements_source === 'llm' ? 'llm' : 'rules')}>by {j.requirements_source}</span></h3>
            <RequirementsTable requirements={j.requirements} />
          </div>
        ))}
        <p className="muted">Matching, scores and the roadmap come in later stages.</p>
      </section>
    </div>
  )
}
