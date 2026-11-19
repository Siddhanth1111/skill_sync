import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { homeFor, useAuth } from '../../auth/AuthContext.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { Field, Input } from '../../components/ui/Form.jsx'
import { Alert } from '../../components/ui/Feedback.jsx'
import AuthLayout from './AuthLayout.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const user = await login(email.trim(), password)
      const from = location.state?.from
      navigate(from && from.startsWith('/' + user.role) ? from : homeFor(user.role), { replace: true })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back. Enter your details to continue."
      footer={<>New to SkillSync? <Link to="/register" className="text-primary hover:underline">Create an account</Link></>}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {error && <Alert color="destructive">{error}</Alert>}
        <Field label="Email">{(p) => <Input {...p} type="email" autoComplete="email" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />}</Field>
        <Field label="Password">
          {(p) => (
            <div className="relative">
              <Input {...p} type={show ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="pr-9" />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          )}
        </Field>
        <Button type="submit" size="lg" loading={busy} disabled={!email || !password}>Sign in</Button>
      </form>
    </AuthLayout>
  )
}
