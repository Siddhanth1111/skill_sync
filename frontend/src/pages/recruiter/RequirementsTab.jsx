import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../../api/index.js'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { Alert } from '../../components/ui/Feedback.jsx'
import RequirementsEditor from '../../components/RequirementsEditor.jsx'
import { useToast } from '../../components/ui/Toast.jsx'

export default function RequirementsTab() {
  const { job, setJob } = useOutletContext()
  const toast = useToast()
  const [saving, setSaving] = useState(false)
  const [showText, setShowText] = useState(false)

  const save = async (patches) => {
    setSaving(true)
    try { setJob(await api.patchRequirements(job.id, patches)); toast.success('Requirements saved.') }
    catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  return (
    <div className="flex flex-col gap-4">
      {job.requirements_source === 'rules' && <Alert color="warning" title="Requirements were read by rules">The language model was unavailable or returned invalid output, so headings and bullets were used. Check that nothing is missing.</Alert>}
      <Card>
        <CardHeader title="Requirements" description="Default weights: must 3, should 2, nice 1. Edit anything before scoring." />
        <RequirementsEditor requirements={job.requirements} onSave={save} saving={saving} />
      </Card>
      <Card>
        <CardHeader title="Original job description" actions={<button className="text-sm text-primary hover:underline" onClick={() => setShowText(!showText)}>{showText ? 'Hide' : 'Show'}</button>} />
        {showText && <pre className="whitespace-pre-wrap p-4 font-sans text-sm text-muted-foreground">{job.text}</pre>}
      </Card>
    </div>
  )
}
