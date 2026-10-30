import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../usePolling.js'
import RequirementsTable from '../components/RequirementsTable.jsx'
import CandidateView from '../components/CandidateView.jsx'
import FileDrop from '../components/FileDrop.jsx'

export default function Recruiter() {
  const [jobs, setJobs] = useState([])
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [status, setStatus] = useState(null)
  const [candidate, setCandidate] = useState(null)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const fail = (e) => setError(e.message)
  const loadJobs = useCallback(() => api.listJobs().then(setJobs).catch(fail), [])
  useEffect(() => { loadJobs() }, [loadJobs])

  const refreshStatus = useCallback(() => (jobId ? api.jobStatus(jobId).then(setStatus) : Promise.resolve()), [jobId])

  useEffect(() => {
    setJob(null); setStatus(null); setCandidate(null); setError('')
    if (jobId == null) return
    api.getJob(jobId).then(setJob).catch(fail)
    refreshStatus().catch(fail)
  }, [jobId, refreshStatus])

  const processing = !!status && status.counts.queued + status.counts.parsing > 0
  usePolling(refreshStatus, processing)

  const createJob = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const j = await api.createJob(title, text)
      setTitle(''); setText('')
      await loadJobs()
      setJobId(j.id)
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const saveRequirements = async (patches) => {
    try { setJob(await api.patchRequirements(jobId, patches)) } catch (err) { fail(err) }
  }

  const upload = async (files) => {
    setError('')
    try { await api.uploadResumes(jobId, files); await refreshStatus() } catch (err) { fail(err) }
  }

  const openCandidate = (id) => api.getCandidate(id).then(setCandidate).catch(fail)

  return (
    <div className="grid">
      <aside>
        <h2>Jobs</h2>
        <button className={jobId == null ? 'item active' : 'item'} onClick={() => setJobId(null)}>+ New job</button>
        {jobs.map((j) => (
          <button key={j.id} className={j.id === jobId ? 'item active' : 'item'} onClick={() => setJobId(j.id)}>
            {j.title} <span className="small">({j.requirements.length} reqs)</span>
          </button>
        ))}
      </aside>

      <section>
        {error && <div className="error">{error}</div>}

        {jobId == null && (
          <form onSubmit={createJob}>
            <h2>New job</h2>
            <input placeholder="Job title" value={title} onChange={(e) => setTitle(e.target.value)} required />
            <textarea rows={14} placeholder="Paste the job description here" value={text}
              onChange={(e) => setText(e.target.value)} required minLength={20} />
            <button className="primary" disabled={busy}>{busy ? 'Extracting requirements...' : 'Extract requirements'}</button>
          </form>
        )}

        {job && (
          <>
            <h2>{job.title}</h2>
            <div className="row">
              <span className={'tag ' + (job.requirements_source === 'llm' ? 'llm' : 'rules')}>
                requirements by {job.requirements_source}
              </span>
              <span className="small">Edit text, importance or weight, then save.</span>
            </div>
            <RequirementsTable requirements={job.requirements} onSave={saveRequirements} />

            <h2>Resumes</h2>
            <FileDrop onFiles={upload} label="Drop up to 200 PDF or DOCX files here, or click to choose" />
            {status && status.total > 0 && (
              <>
                <div className="row counts">
                  {Object.entries(status.counts).map(([k, v]) => <span key={k} className={'tag ' + k}>{k}: {v}</span>)}
                  {processing && <span className="small">updating...</span>}
                </div>
                <table>
                  <thead><tr><th>File</th><th>Status</th><th>Source</th><th>Notes</th><th /></tr></thead>
                  <tbody>
                    {status.files.map((f) => (
                      <tr key={f.id}>
                        <td>{f.filename}</td>
                        <td><span className={'tag ' + f.status}>{f.status}</span></td>
                        <td>{f.source || '-'}</td>
                        <td className="small">
                          {f.error}
                          {f.needs_ocr && ' OCR used. '}
                          {f.parse_confidence?.low && ' low confidence'}
                        </td>
                        <td>{f.status === 'done' && <button onClick={() => openCandidate(f.id)}>View</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            {candidate && (
              <div className="panel">
                <button className="close" onClick={() => setCandidate(null)}>close</button>
                <CandidateView candidate={candidate} />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
