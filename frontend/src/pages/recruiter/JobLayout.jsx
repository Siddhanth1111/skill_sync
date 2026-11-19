import { useState } from 'react'
import { Link, Outlet, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Download, Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge, SourceBadge } from '../../components/ui/Badge.jsx'
import { PageHeader, TabNav } from '../../components/ui/Layout.jsx'
import { Dialog } from '../../components/ui/Overlay.jsx'
import { ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { useToast } from '../../components/ui/Toast.jsx'

// Frame for one job: header, route-driven tabs, and the job shared with every tab through outlet context.
export default function JobLayout() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const job = useApi(() => api.job(jobId), [jobId])
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  const exportCsv = async () => {
    try {
      const blob = await api.exportCsv(jobId)
      const url = URL.createObjectURL(blob)
      Object.assign(document.createElement('a'), { href: url, download: `skillsync-job-${jobId}-ranking.csv` }).click()
      URL.revokeObjectURL(url)
    } catch (e) { toast.error(e.message) }
  }
  const remove = async () => {
    setBusy(true)
    try { await api.deleteJob(jobId); toast.success('Job deleted.'); navigate('/recruiter/jobs') } catch (e) { toast.error(e.message); setBusy(false) }
  }

  if (job.error) return <div className="p-4"><ErrorState error={job.error} onRetry={job.reload} /></div>
  const j = job.data
  const base = `/recruiter/jobs/${jobId}`
  return (
    <>
      <PageHeader
        eyebrow={<Link to="/recruiter/jobs" className="inline-flex items-center gap-0.5 hover:text-foreground"><ChevronLeft className="size-3" />Jobs</Link>}
        title={j ? j.title : <Skeleton className="h-6 w-64" />}
        description={j && <span className="inline-flex items-center gap-2"><SourceBadge source={j.requirements_source} label={`Requirements by ${j.requirements_source === 'llm' ? 'language model' : 'rules'}`} />{j.scores_stale && <Badge color="warning">Scores out of date</Badge>}</span>}
        actions={<><Button variant="outline" leftIcon={<Download />} onClick={exportCsv}>Export CSV</Button><Button variant="transparent" iconOnly aria-label="Delete job" onClick={() => setConfirm(true)}><Trash2 /></Button></>} />
      <TabNav tabs={[
        { to: base, label: 'Requirements', end: true, badge: j?.requirements.length },
        { to: `${base}/resumes`, label: 'Resumes', badge: j?.candidate_count },
        { to: `${base}/ranking`, label: 'Ranking' },
        { to: `${base}/fairness`, label: 'Fairness' },
        { to: `${base}/learning`, label: 'Learning' },
        { to: `${base}/analytics`, label: 'Analytics' },
      ]} />
      <div className="p-4">{j ? <Outlet context={{ job: j, setJob: job.setData, reloadJob: () => job.reload(true) }} /> : <Skeleton className="h-64" />}</div>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Delete this job?"
        description={j && `"${j.title}" and its ${j.candidate_count} resumes, scores, ratings and audits will be permanently deleted.`}
        footer={<><Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="destructive" loading={busy} onClick={remove}>Delete job</Button></>} />
    </>
  )
}
