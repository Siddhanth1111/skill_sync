import { useCallback, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Eye, Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi, usePolling } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge, FileStatusBadge, SourceBadge } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { DataTable } from '../../components/ui/Layout.jsx'
import { EmptyState, Progress, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { Dialog, Sheet } from '../../components/ui/Overlay.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import FileDrop from '../../components/FileDrop.jsx'
import CandidateProfile from '../../components/CandidateProfile.jsx'

export default function ResumesTab() {
  const { job, reloadJob } = useOutletContext()
  const toast = useToast()
  const status = useApi(() => api.jobStatus(job.id), [job.id])
  const [uploading, setUploading] = useState(false)
  const [view, setView] = useState(null)
  const [del, setDel] = useState(null)

  const s = status.data
  const working = !!s && s.counts.queued + s.counts.parsing > 0
  const refresh = useCallback(async () => { await status.reload(true); reloadJob() }, [status.reload]) // eslint-disable-line
  usePolling(refresh, working, 1500)

  const upload = async (files) => {
    setUploading(true)
    try {
      const rows = await api.uploadResumes(job.id, files)
      const bad = rows.filter((r) => r.status === 'failed').length
      toast[bad === rows.length ? 'error' : 'success'](bad ? `${rows.length - bad} queued, ${bad} rejected. See the reasons below.` : `${rows.length} resume${rows.length > 1 ? 's' : ''} queued.`)
      await refresh()
    } catch (e) { toast.error(e.message) } finally { setUploading(false) }
  }
  const open = async (f) => {
    try { setView(await api.candidate(f.id)) } catch (e) { toast.error(e.message) }
  }
  const remove = async () => {
    try { await api.deleteCandidate(del.id); toast.success('Resume deleted.'); setDel(null); refresh() } catch (e) { toast.error(e.message) }
  }

  const done = s ? s.counts.done + s.counts.failed : 0
  return (
    <div className="flex flex-col gap-4">
      <FileDrop onFiles={upload} disabled={uploading} title="Drop up to 200 PDF or DOCX resumes here, or click to choose" />
      <Card>
        <CardHeader title="Uploaded resumes" description={s ? `${s.counts.done} parsed, ${s.counts.failed} failed, ${s.counts.queued + s.counts.parsing} in progress` : undefined}
          actions={s && s.total > 0 && <Badge color="neutral">{s.total} total</Badge>} />
        {working && <div className="px-4 pt-3"><Progress value={done} max={s.total} label="Parsing progress" /><p className="mt-1 text-xs text-muted-foreground">Parsing {done} of {s.total}. Up to 3 resumes are read at a time, so a large batch takes a while.</p></div>}
        {status.loading ? <SkeletonRows rows={3} /> : (
          <DataTable rows={s?.files || []} rowKey={(f) => f.id}
            columns={[
              { key: 'f', header: 'File', render: (f) => <span className="font-medium">{f.filename}</span> },
              { key: 's', header: 'Status', width: '8rem', render: (f) => <FileStatusBadge status={f.status} /> },
              { key: 'src', header: 'Read by', width: '10rem', render: (f) => f.source ? <SourceBadge source={f.source} /> : '-' },
              { key: 'n', header: 'Notes', render: (f) => <span className="text-muted-foreground">{f.error}{f.needs_ocr && 'OCR used. '}{f.parse_confidence?.low && !f.error && 'Low parse confidence'}</span> },
              { key: 'a', header: '', width: '5.5rem', render: (f) => (
                <div className="flex justify-end gap-1">
                  {f.status === 'done' && <Button variant="transparent" size="sm" iconOnly aria-label={`View ${f.filename}`} onClick={() => open(f)}><Eye /></Button>}
                  <Button variant="transparent" size="sm" iconOnly aria-label={`Delete ${f.filename}`} onClick={() => setDel(f)}><Trash2 /></Button>
                </div>) },
            ]}
            empty={<EmptyState title="No resumes yet">Upload resumes above. After they are parsed, open the Ranking tab and run scoring.</EmptyState>} />
        )}
      </Card>
      <Sheet open={!!view} onClose={() => setView(null)} title={view?.profile?.name || view?.filename || 'Resume'} subtitle="What was read from this resume">
        {view && <CandidateProfile candidate={view} />}
      </Sheet>
      <Dialog open={!!del} onClose={() => setDel(null)} title="Delete this resume?" description={del && `${del.filename} and its scores and rating will be deleted.`}
        footer={<><Button variant="outline" onClick={() => setDel(null)}>Cancel</Button><Button variant="destructive" onClick={remove}>Delete resume</Button></>} />
    </div>
  )
}
