import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Briefcase, Plus, Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { DataTable, PageHeader } from '../../components/ui/Layout.jsx'
import { EmptyState, ErrorState, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { Dialog } from '../../components/ui/Overlay.jsx'
import { SourceBadge } from '../../components/ui/Badge.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import { formatDate } from '../../lib/utils.js'

export default function Jobs() {
  const jobs = useApi(() => api.jobs())
  const navigate = useNavigate()
  const toast = useToast()
  const [target, setTarget] = useState(null)
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    setBusy(true)
    try { await api.deleteJob(target.id); toast.success(`Deleted "${target.title}".`); setTarget(null); jobs.reload(true) }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Jobs" description="Each job has its own requirements, resumes, ranking and audits."
        actions={<Link to="/recruiter/jobs/new"><Button leftIcon={<Plus />}>New job</Button></Link>} />
      <div className="px-4">
        {jobs.error && <ErrorState error={jobs.error} onRetry={jobs.reload} />}
        <Card>
          {jobs.loading ? <SkeletonRows /> : (
            <DataTable rows={jobs.data || []} rowKey={(j) => j.id} onRowClick={(j) => navigate(`/recruiter/jobs/${j.id}`)}
              columns={[
                { key: 'title', header: 'Job', render: (j) => <span className="font-medium">{j.title}</span> },
                { key: 'src', header: 'Requirements by', width: '11rem', render: (j) => <SourceBadge source={j.requirements_source} /> },
                { key: 'req', header: 'Requirements', width: '8rem', align: 'right', render: (j) => j.requirements.length },
                { key: 'res', header: 'Resumes parsed', width: '9rem', align: 'right', render: (j) => `${j.parsed_count} / ${j.candidate_count}` },
                { key: 'created', header: 'Created', width: '9rem', render: (j) => formatDate(j.created_at) },
                { key: 'act', header: '', width: '3rem', render: (j) => <Button variant="transparent" iconOnly size="sm" aria-label={`Delete ${j.title}`} onClick={(e) => { e.stopPropagation(); setTarget(j) }}><Trash2 /></Button> },
              ]}
              empty={<EmptyState icon={Briefcase} title="No jobs yet" action={<Link to="/recruiter/jobs/new"><Button>Create a job</Button></Link>}>Paste a job description to get started.</EmptyState>} />
          )}
        </Card>
      </div>
      <Dialog open={!!target} onClose={() => setTarget(null)} title="Delete this job?"
        description={target && `"${target.title}" and its ${target.candidate_count} resumes, scores, ratings and audits will be permanently deleted.`}
        footer={<><Button variant="outline" onClick={() => setTarget(null)}>Cancel</Button><Button variant="destructive" loading={busy} onClick={remove}>Delete job</Button></>} />
    </>
  )
}
