import { useState } from 'react'
import { api } from '../../api/index.js'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { Alert, ErrorState, Skeleton } from '../../components/ui/Feedback.jsx'
import { PageHeader } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import CandidateProfile from '../../components/CandidateProfile.jsx'
import FileDrop from '../../components/FileDrop.jsx'
import { useResume } from './useResume.js'

export default function Resume() {
  const resume = useResume()
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  const upload = async (files) => {
    setBusy(true)
    try {
      const r = await api.uploadStudentResume(files[0])
      if (r.status === 'failed') toast.error(r.error)
      await resume.reload(true)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const r = resume.data

  return (
    <>
      <PageHeader title="My resume" description="Upload one resume. A new upload replaces the current one and clears old match results." />
      <div className="flex flex-col gap-4 px-4">
        <FileDrop multiple={false} disabled={busy} onFiles={upload} />
        {resume.error && <ErrorState error={resume.error} onRetry={resume.reload} />}
        {resume.loading && <Skeleton className="h-40" />}
        {r && (r.status === 'queued' || r.status === 'parsing') && <Alert>Reading your resume. This usually takes under a minute.</Alert>}
        {r && (r.status === 'done' || r.status === 'failed') && (
          <Card><CardHeader title={r.profile?.name || r.filename} description="What was read from your resume. If something is wrong here, it affects your match." />
            <div className="p-4"><CandidateProfile candidate={r} /></div></Card>
        )}
      </div>
    </>
  )
}
