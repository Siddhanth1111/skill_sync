import { useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Badge } from '../../components/ui/Badge.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { EmptyState, ErrorState, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { Select } from '../../components/ui/Form.jsx'
import { DataTable, PageHeader } from '../../components/ui/Layout.jsx'
import { formatDateTime } from '../../lib/utils.js'

const ACTIONS = ['register', 'login', 'job_created', 'job_deleted', 'resumes_uploaded', 'scoring_started', 'audit_run', 'model_trained', 'student_resume_uploaded', 'student_match', 'student_whatif', 'data_deleted', 'user_deleted']
const TONE = { data_deleted: 'destructive', user_deleted: 'destructive', login: 'neutral', register: 'success' }

export default function Activity() {
  const [action, setAction] = useState('')
  const log = useApi(() => api.adminActivity(action), [action])
  return (
    <>
      <PageHeader title="Activity log" description="The latest 200 events. Details are ids and counts only, never resume text or personal data." />
      <div className="px-4">
        {log.error && <ErrorState error={log.error} onRetry={log.reload} />}
        <Card>
          <div className="flex items-center gap-2 border-b border-border p-3">
            <Select value={action} onChange={(e) => setAction(e.target.value)} className="w-56" aria-label="Filter by action"><option value="">All actions</option>{ACTIONS.map((a) => <option key={a} value={a}>{a.replaceAll('_', ' ')}</option>)}</Select>
          </div>
          {log.loading ? <SkeletonRows /> : (
            <DataTable rows={log.data || []} rowKey={(r) => r.id} columns={[
              { key: 't', header: 'When', width: '11rem', render: (r) => formatDateTime(r.created_at) },
              { key: 'u', header: 'User', render: (r) => r.email || <span className="text-muted-foreground">deleted user {r.user_id}</span> },
              { key: 'a', header: 'Action', width: '14rem', render: (r) => <Badge color={TONE[r.action] || 'neutral'}>{r.action.replaceAll('_', ' ')}</Badge> },
              { key: 'd', header: 'Detail', render: (r) => <span className="font-mono text-xs text-muted-foreground">{r.detail}</span> },
            ]} empty={<EmptyState title="No activity">Nothing matches this filter.</EmptyState>} />
          )}
        </Card>
      </div>
    </>
  )
}
