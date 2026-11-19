import { useState } from 'react'
import { Briefcase, ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { SourceBadge } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { Field, Input, Textarea } from '../../components/ui/Form.jsx'
import { Alert, EmptyState, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { PageHeader } from '../../components/ui/Layout.jsx'
import { Dialog } from '../../components/ui/Overlay.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import RequirementsEditor from '../../components/RequirementsEditor.jsx'

export default function Jobs() {
  const jobs = useApi(() => api.jobs())
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(null)
  const [del, setDel] = useState(null)

  const add = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const j = await api.createJob(title.trim() || 'Untitled job', text)
      toast.success(`Added with ${j.requirements.length} requirements.`)
      setTitle(''); setText(''); setOpen(j.id); await jobs.reload(true)
    } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }
  const remove = async () => {
    try { await api.deleteJob(del.id); toast.success('Job removed.'); setDel(null); jobs.reload(true) } catch (e) { toast.error(e.message) }
  }

  return (
    <>
      <PageHeader title="Job descriptions" description="Paste the jobs you are interested in. Each is split into requirements your resume is scored against." />
      <div className="grid gap-4 px-4 lg:grid-cols-[2fr_3fr]">
        <Card className="self-start">
          <CardHeader title="Add a job description" />
          <form onSubmit={add} className="flex flex-col gap-3 p-4">
            <Field label="Job title (optional)">{(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Data Analyst" />}</Field>
            <Field label="Job description">{(p) => <Textarea {...p} required minLength={20} rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full job description" />}</Field>
            {busy && <Alert>Reading the description. This can take up to a minute.</Alert>}
            <Button type="submit" loading={busy} disabled={text.trim().length < 20}>Add job description</Button>
          </form>
        </Card>

        <Card className="self-start">
          <CardHeader title={`Your jobs (${jobs.data?.length || 0})`} />
          {jobs.loading ? <SkeletonRows rows={3} /> : !jobs.data?.length ? <EmptyState icon={Briefcase} title="No job descriptions yet">Add one on the left. Then match your resume against it.</EmptyState> : (
            <ul className="divide-y divide-border">
              {jobs.data.map((j) => (
                <li key={j.id}>
                  <div className="flex items-center gap-2 px-4 py-3">
                    <button onClick={() => setOpen(open === j.id ? null : j.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left" aria-expanded={open === j.id}>
                      {open === j.id ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
                      <span className="truncate font-medium">{j.title}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{j.requirements.length} requirements</span>
                    </button>
                    <SourceBadge source={j.requirements_source} />
                    <Button variant="transparent" size="sm" iconOnly aria-label={`Delete ${j.title}`} onClick={() => setDel(j)}><Trash2 /></Button>
                  </div>
                  {open === j.id && <div className="border-t border-border bg-muted/20"><RequirementsEditor requirements={j.requirements} /></div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Dialog open={!!del} onClose={() => setDel(null)} title="Remove this job?" description={del && `"${del.title}" and its match results will be deleted.`}
        footer={<><Button variant="outline" onClick={() => setDel(null)}>Cancel</Button><Button variant="destructive" onClick={remove}>Remove</Button></>} />
    </>
  )
}
