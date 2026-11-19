import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { api } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { Avatar } from '../components/ui/Avatar.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Button } from '../components/ui/Button.jsx'
import { Card, CardHeader } from '../components/ui/Card.jsx'
import { Input } from '../components/ui/Form.jsx'
import { PageHeader } from '../components/ui/Layout.jsx'
import { Dialog } from '../components/ui/Overlay.jsx'
import { useToast } from '../components/ui/Toast.jsx'

export default function Settings() {
  const { user, signOut } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [mode, setMode] = useState(null) // 'data' | 'account'
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const isAdmin = user.role === 'admin'

  const close = () => { setMode(null); setConfirm('') }
  const go = async () => {
    setBusy(true)
    try {
      const r = await api.deleteMyData(mode === 'account')
      if (mode === 'account') { signOut(); navigate('/login'); return }
      toast.success(`Deleted ${r.jobs} jobs and ${r.candidates} resumes.`); close()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Settings" description="Your account and your data." />
      <div className="flex max-w-3xl flex-col gap-4 px-4">
        <Card>
          <CardHeader title="Account" />
          <div className="flex items-center gap-4 p-4">
            <Avatar name={user.full_name || user.email} className="size-12 text-sm" />
            <div><p className="font-medium">{user.full_name || 'No name set'}</p><p className="text-sm text-muted-foreground">{user.email}</p></div>
            <Badge color="accent" className="ml-auto capitalize">{user.role}</Badge>
          </div>
        </Card>
        <Card>
          <CardHeader title="Privacy and data" description="Resumes are stored so they can be scored. Only you can see them. Use synthetic or consented resumes only." />
          <div className="divide-y divide-border">
            {!isAdmin && (
              <div className="flex items-center gap-4 p-4">
                <div className="flex-1"><p className="font-medium">Delete all my data</p><p className="text-sm text-muted-foreground">Removes every job, resume, score, rating and audit. Your account stays.</p></div>
                <Button variant="outline" leftIcon={<Trash2 />} onClick={() => setMode('data')}>Delete data</Button>
              </div>
            )}
            <div className="flex items-center gap-4 p-4">
              <div className="flex-1"><p className="font-medium">Delete my account</p><p className="text-sm text-muted-foreground">Removes your account and everything above. This cannot be undone.</p></div>
              <Button variant="destructive" onClick={() => setMode('account')}>Delete account</Button>
            </div>
          </div>
        </Card>
      </div>
      <Dialog open={!!mode} onClose={close} title={mode === 'account' ? 'Delete your account?' : 'Delete all your data?'}
        description={mode === 'account' ? 'Your account, jobs, resumes, scores, ratings and audits will be permanently deleted.' : 'All of your jobs, resumes, scores, ratings and audits will be permanently deleted.'}
        footer={<><Button variant="outline" onClick={close}>Cancel</Button><Button variant="destructive" loading={busy} disabled={confirm !== 'DELETE'} onClick={go}>{mode === 'account' ? 'Delete account' : 'Delete data'}</Button></>}>
        <label className="flex flex-col gap-1.5 text-sm">Type <b>DELETE</b> to confirm<Input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" /></label>
      </Dialog>
    </>
  )
}
