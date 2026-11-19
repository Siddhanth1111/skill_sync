import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { usePolling } from '../usePolling.js'
import RequirementsTable from './RequirementsTable.jsx'
import CandidateView from './CandidateView.jsx'
import FileDrop from './FileDrop.jsx'

// Stages 1 to 5 for one job: edit requirements, upload resumes, watch parsing, inspect a parsed resume.
export default function JobSetup({ job, onJobChange, onError }) {
  const [status, setStatus] = useState(null)
  const [candidate, setCandidate] = useState(null)

  const refreshStatus = useCallback(() => api.jobStatus(job.id).then(setStatus), [job.id])
  useEffect(() => { setCandidate(null); refreshStatus().catch((e) => onError(e.message)) }, [refreshStatus]) // eslint-disable-line

  const processing = !!status && status.counts.queued + status.counts.parsing > 0
  usePolling(refreshStatus, processing)

  const save = async (patches) => {
    try { onJobChange(await api.patchRequirements(job.id, patches)) } catch (e) { onError(e.message) }
  }
  const upload = async (files) => {
    try { await api.uploadResumes(job.id, files); await refreshStatus() } catch (e) { onError(e.message) }
  }

  return (
    <>
      <div className="row">
        <span className={'tag ' + (job.requirements_source === 'llm' ? 'llm' : 'rules')}>requirements by {job.requirements_source}</span>
        <span className="small">Edit text, importance or weight, then save. Changing the wording means scoring must be re-run.</span>
      </div>
      <RequirementsTable requirements={job.requirements} onSave={save} />

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
                  <td className="small">{f.error}{f.needs_ocr && ' OCR used. '}{f.parse_confidence?.low && ' low confidence'}</td>
                  <td>{f.status === 'done' && <button onClick={() => api.getCandidate(f.id).then(setCandidate).catch((e) => onError(e.message))}>View</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">When parsing is done, open the <b>Ranking</b> tab and run scoring.</p>
        </>
      )}
      {candidate && (
        <div className="panel"><button className="close" onClick={() => setCandidate(null)}>close</button><CandidateView candidate={candidate} /></div>
      )}
    </>
  )
}
