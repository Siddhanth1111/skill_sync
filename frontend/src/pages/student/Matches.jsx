import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Target } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { ScoreBar } from '../../components/ui/Charts.jsx'
import { Alert, EmptyState, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { DataTable, PageHeader } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import { useNavigate } from 'react-router-dom'
import { useResume } from './useResume.js'

export default function Matches() {
  const resume = useResume()
  const jobs = useApi(() => api.jobs())
  const matches = useApi(() => api.studentMatches())
  const toast = useToast()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  const ready = resume.data?.status === 'done'
  const run = async () => {
    setBusy(true)
    try { matches.setData(await api.studentMatch(resume.data.id, jobs.data.map((j) => j.id))); toast.success('Match complete.') }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const noJobs = !jobs.loading && !jobs.data?.length

  return (
    <>
      <PageHeader title="Matches and roadmap" description="Your resume scored against each job description, best match first."
        actions={<Button leftIcon={<Target />} loading={busy} disabled={!ready || noJobs} onClick={run}>{matches.data?.length ? 'Re-run match' : 'Match my resume'}</Button>} />
      <div className="flex flex-col gap-4 px-4">
        {!resume.loading && !ready && <Alert color="warning" title="Resume not ready">{resume.data ? 'Your resume is still being read.' : 'Upload your resume first.'} <Link className="underline" to="/student/resume">Go to My resume</Link></Alert>}
        {noJobs && <Alert color="warning" title="No job descriptions">Add at least one. <Link className="underline" to="/student/jobs">Go to Job descriptions</Link></Alert>}
        <Card>
          <CardHeader title="Results" description="Open a job for your roadmap and what-if simulator." />
          {matches.loading ? <SkeletonRows rows={3} /> : (
            <DataTable rows={matches.data || []} rowKey={(m) => m.job_id} onRowClick={(m) => navigate(`/student/matches/${m.job_id}`)}
              columns={[
                { key: 'i', header: '#', width: '3rem', render: (m) => <span className="tabular-nums text-muted-foreground">{matches.data.indexOf(m) + 1}</span> },
                { key: 't', header: 'Job', render: (m) => <span className="font-medium">{m.title}</span> },
                { key: 's', header: 'Match', width: '14rem', render: (m) => <ScoreBar value={m.final_score} /> },
                { key: 'm', header: 'Met', width: '4rem', align: 'right', render: (m) => m.met },
                { key: 'p', header: 'Partial', width: '4.5rem', align: 'right', render: (m) => m.partial },
                { key: 'x', header: 'Missing', width: '5rem', align: 'right', render: (m) => m.not_met },
                { key: 'u', header: 'Musts met', width: '6rem', align: 'right', render: (m) => `${m.musts_met} / ${m.musts}` },
              ]}
              empty={<EmptyState icon={Target} title="No matches yet">Run the match to score your resume against your job descriptions.</EmptyState>} />
          )}
        </Card>
      </div>
    </>
  )
}
