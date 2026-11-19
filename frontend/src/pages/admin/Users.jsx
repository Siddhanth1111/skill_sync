import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { Avatar } from '../../components/ui/Avatar.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { Card } from '../../components/ui/Card.jsx'
import { ErrorState, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { Input } from '../../components/ui/Form.jsx'
import { DataTable, PageHeader } from '../../components/ui/Layout.jsx'
import { Dialog } from '../../components/ui/Overlay.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import { formatDate, formatDateTime } from '../../lib/utils.js'

export default function Users() {
  const { user: me } = useAuth()
  const users = useApi(() => api.adminUsers())
  const toast = useToast()
  const [target, setTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')

  const rows = (users.data || []).filter((u) => `${u.email} ${u.full_name || ''} ${u.role}`.toLowerCase().includes(filter.toLowerCase()))
  const remove = async () => {
    setBusy(true)
    try { const r = await api.adminDeleteUser(target.id); toast.success(`Deleted ${target.email} with ${r.jobs} jobs and ${r.candidates} resumes.`); setTarget(null); users.reload(true) }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <>
      <PageHeader title="Users" description="Removing a user permanently deletes their jobs, resumes, scores, ratings and audits." />
      <div className="flex flex-col gap-4 px-4">
        {users.error && <ErrorState error={users.error} onRetry={users.reload} />}
        <Card>
          <div className="border-b border-border p-3"><Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name, email or role" aria-label="Filter users" className="max-w-sm" /></div>
          {users.loading ? <SkeletonRows /> : (
            <DataTable rows={rows} rowKey={(u) => u.id} columns={[
              { key: 'u', header: 'User', render: (u) => <div className="flex items-center gap-2"><Avatar name={u.full_name || u.email} size="sm" /><div className="min-w-0"><p className="truncate font-medium">{u.full_name || u.email}</p>{u.full_name && <p className="truncate text-xs text-muted-foreground">{u.email}</p>}</div></div> },
              { key: 'r', header: 'Role', width: '8rem', render: (u) => <Badge color={u.role === 'admin' ? 'accent' : 'neutral'} className="capitalize">{u.role}</Badge> },
              { key: 'j', header: 'Jobs', width: '5rem', align: 'right', render: (u) => u.jobs }, { key: 'c', header: 'Resumes', width: '6rem', align: 'right', render: (u) => u.candidates },
              { key: 'l', header: 'Last sign-in', width: '11rem', render: (u) => formatDateTime(u.last_login) }, { key: 'd', header: 'Joined', width: '9rem', render: (u) => formatDate(u.created_at) },
              { key: 'x', header: '', width: '3rem', render: (u) => u.id !== me.id && <Button variant="transparent" size="sm" iconOnly aria-label={`Delete ${u.email}`} onClick={() => setTarget(u)}><Trash2 /></Button> },
            ]} />
          )}
        </Card>
      </div>
      <Dialog open={!!target} onClose={() => setTarget(null)} title="Delete this user?"
        description={target && `${target.email} and all of their data (${target.jobs} jobs, ${target.candidates} resumes) will be permanently deleted. This cannot be undone.`}
        footer={<><Button variant="outline" onClick={() => setTarget(null)}>Cancel</Button><Button variant="destructive" loading={busy} onClick={remove}>Delete user</Button></>} />
    </>
  )
}
