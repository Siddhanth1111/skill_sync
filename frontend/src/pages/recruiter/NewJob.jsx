import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { api } from '../../api/index.js'
import { Button } from '../../components/ui/Button.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { Field, Input, Textarea } from '../../components/ui/Form.jsx'
import { Alert } from '../../components/ui/Feedback.jsx'
import { PageHeader } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'

const SAMPLE = `Backend Engineer

Requirements
- 3+ years of experience building backend services
- Strong Python and SQL skills
- Bachelor's degree in Computer Science

Nice to have
- Experience with Kafka

Benefits
- Free lunch and health insurance`

export default function NewJob() {
  const navigate = useNavigate()
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const job = await api.createJob(title.trim(), text)
      toast.success(`Extracted ${job.requirements.length} requirements.`)
      navigate(`/recruiter/jobs/${job.id}`)
    } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <>
      <PageHeader title="New job" description="Paste the job description. It is split into requirements you can edit before any resume is scored." />
      <div className="px-4">
        <Card className="mx-auto max-w-3xl">
          <form onSubmit={submit} className="flex flex-col gap-4 p-4">
            {error && <Alert color="destructive" title="Unable to create the job">{error}</Alert>}
            <Field label="Job title">{(p) => <Input {...p} required maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Backend Engineer" autoFocus />}</Field>
            <Field label="Job description" hint="Benefits, perks and legal text are ignored. Include every qualification, including nice-to-haves.">
              {(p) => <Textarea {...p} required minLength={20} rows={16} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full job description here" />}
            </Field>
            {busy && <Alert>Reading the description with the language model. This can take up to a minute.</Alert>}
            <div className="flex items-center justify-between gap-2">
              <Button variant="transparent" leftIcon={<Sparkles />} onClick={() => { setTitle('Backend Engineer'); setText(SAMPLE) }}>Use a sample</Button>
              <div className="flex gap-2">
                <Link to="/recruiter/jobs"><Button variant="outline">Cancel</Button></Link>
                <Button type="submit" loading={busy} disabled={!title.trim() || text.trim().length < 20}>Extract requirements</Button>
              </div>
            </div>
          </form>
        </Card>
      </div>
    </>
  )
}
