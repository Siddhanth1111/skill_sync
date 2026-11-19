import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { Input, Select } from '../../components/ui/Form.jsx'
import { Alert, EmptyState } from '../../components/ui/Feedback.jsx'
import { PageHeader } from '../../components/ui/Layout.jsx'

export default function SearchPage() {
  const jobs = useApi(() => api.jobs())
  const [q, setQ] = useState('')
  const [jobId, setJobId] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { setRes(await api.search(q.trim(), jobId)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Search resumes" description="Search by meaning across the resumes you uploaded, for example 'led a data engineering team' or 'built streaming pipelines'." />
      <div className="flex flex-col gap-4 px-4">
        <Card>
          <form onSubmit={submit} className="flex flex-wrap gap-2 p-4">
            <div className="min-w-64 flex-1"><Input prefix={<Search />} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Describe what you are looking for" aria-label="Search query" /></div>
            <Select value={jobId} onChange={(e) => setJobId(e.target.value)} className="w-56" aria-label="Limit to job"><option value="">All jobs</option>{(jobs.data || []).map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</Select>
            <Button type="submit" loading={busy} disabled={q.trim().length < 2}>Search</Button>
          </form>
        </Card>
        {error && <Alert color="destructive">{error}</Alert>}
        {res && (res.results.length === 0
          ? <Card><EmptyState title="No matching resumes">{res.searched === 0 ? 'No resume segments have been indexed yet. Upload and parse resumes first.' : 'Try describing the skill or experience differently.'}</EmptyState></Card>
          : <div className="flex flex-col gap-2">
              <p className="px-1 text-xs text-muted-foreground">Best passage per candidate, from {res.searched} indexed segments.</p>
              {res.results.map((r) => (
                <Card key={r.candidate_id} className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/recruiter/jobs/${r.job_id}/ranking?candidate=${r.candidate_id}`} className="font-medium hover:text-primary">{r.name}</Link>
                    <Badge color="neutral">{r.job_title}</Badge><Badge color="accent" className="capitalize">{r.section}</Badge>
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">similarity {r.similarity.toFixed(2)}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{r.text}</p>
                </Card>
              ))}
            </div>)}
      </div>
    </>
  )
}
