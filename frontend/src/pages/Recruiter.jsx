import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import JobSetup from '../components/JobSetup.jsx'
import RankingTab from '../components/RankingTab.jsx'
import FairnessTab from '../components/FairnessTab.jsx'
import LearningTab from '../components/LearningTab.jsx'

const TABS = [
  ['setup', 'Requirements and resumes'],
  ['ranking', 'Ranking'],
  ['fairness', 'Fairness'],
  ['learning', 'Learning'],
]

export default function Recruiter() {
  const [jobs, setJobs] = useState([])
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [tab, setTab] = useState('setup')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadJobs = useCallback(() => api.listJobs('recruiter').then(setJobs).catch((e) => setError(e.message)), [])
  useEffect(() => { loadJobs() }, [loadJobs])
  useEffect(() => {
    setJob(null); setError(''); setTab('setup')
    if (jobId != null) api.getJob(jobId).then(setJob).catch((e) => setError(e.message))
  }, [jobId])

  const createJob = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const j = await api.createJob(title, text, 'recruiter')
      setTitle(''); setText('')
      await loadJobs()
      setJobId(j.id)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const onJobChange = (j) => { setJob(j); loadJobs() }

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
            <textarea rows={14} placeholder="Paste the job description here" value={text} onChange={(e) => setText(e.target.value)} required minLength={20} />
            <button className="primary" disabled={busy}>{busy ? 'Extracting requirements...' : 'Extract requirements'}</button>
          </form>
        )}

        {job && (
          <>
            <h2>{job.title}</h2>
            <nav className="subtabs">
              {TABS.map(([k, label]) => <button key={k} className={tab === k ? 'tab active' : 'tab'} onClick={() => { setTab(k); setError('') }}>{label}</button>)}
            </nav>
            {tab === 'setup' && <JobSetup key={job.id} job={job} onJobChange={onJobChange} onError={setError} />}
            {tab === 'ranking' && <RankingTab key={job.id} job={job} onJobChange={onJobChange} onError={setError} />}
            {tab === 'fairness' && <FairnessTab key={job.id} job={job} onError={setError} />}
            {tab === 'learning' && <LearningTab key={job.id} job={job} onError={setError} />}
          </>
        )}
      </section>
    </div>
  )
}
