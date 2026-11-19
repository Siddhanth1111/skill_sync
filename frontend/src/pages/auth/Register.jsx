import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Briefcase, GraduationCap } from 'lucide-react'
import { homeFor, useAuth } from '../../auth/AuthContext.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { Field, Input } from '../../components/ui/Form.jsx'
import { Alert } from '../../components/ui/Feedback.jsx'
import { cn } from '../../lib/utils.js'
import AuthLayout from './AuthLayout.jsx'

const ROLES = [
  { value: 'recruiter', icon: Briefcase, title: 'Recruiter', body: 'Rank resumes for a job' },
  { value: 'student', icon: GraduationCap, title: 'Student', body: 'Match your resume to jobs' },
]

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ role: 'recruiter', full_name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const weak = form.password.length > 0 && form.password.length < 8

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const user = await register({ ...form, email: form.email.trim() })
      navigate(homeFor(user.role), { replace: true })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Choose how you will use SkillSync."
      footer={<>Already have an account? <Link to="/login" className="text-primary hover:underline">Sign in</Link></>}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {error && <Alert color="destructive">{error}</Alert>}
        <fieldset className="grid grid-cols-2 gap-2">
          <legend className="mb-1.5 text-sm font-medium">I am a</legend>
          {ROLES.map(({ value, icon: Icon, title, body }) => (
            <label key={value} className={cn('flex cursor-pointer flex-col gap-1 rounded-lg border p-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring',
              form.role === value ? 'border-primary bg-accent' : 'border-border-subtle bg-card hover:bg-muted/40')}>
              <input type="radio" name="role" value={value} checked={form.role === value} onChange={set('role')} className="sr-only" />
              <Icon className={cn('size-4', form.role === value ? 'text-primary' : 'text-muted-foreground')} aria-hidden />
              <span className="text-sm font-medium">{title}</span>
              <span className="text-xs text-muted-foreground">{body}</span>
            </label>
          ))}
        </fieldset>
        <Field label="Full name">{(p) => <Input {...p} autoComplete="name" value={form.full_name} onChange={set('full_name')} placeholder="Your name" />}</Field>
        <Field label="Email">{(p) => <Input {...p} type="email" autoComplete="email" required value={form.email} onChange={set('email')} placeholder="you@company.com" />}</Field>
        <Field label="Password" hint="8 to 72 characters." error={weak ? 'Use at least 8 characters.' : undefined}>
          {(p) => <Input {...p} type="password" autoComplete="new-password" required error={weak} value={form.password} onChange={set('password')} />}
        </Field>
        <Button type="submit" size="lg" loading={busy} disabled={!form.email || form.password.length < 8}>Create account</Button>
      </form>
    </AuthLayout>
  )
}
