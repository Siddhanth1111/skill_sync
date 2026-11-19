import { CheckCircle2, ShieldCheck, UserCheck } from 'lucide-react'

const POINTS = [
  [CheckCircle2, 'Every quotation is verified', 'A quote is shown only if it appears word for word in the resume.'],
  [UserCheck, 'People make the decision', 'Scores are evidence for a reviewer. Nothing approves or rejects a candidate.'],
  [ShieldCheck, 'Fairness checks built in', 'Blind, counterfactual, adverse-impact and embedding-bias audits, with their limits stated.'],
]

export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="grid min-h-full bg-background lg:grid-cols-2">
      <div className="hidden flex-col justify-between border-r border-border bg-card p-10 lg:flex">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-md bg-primary text-base font-semibold text-primary-foreground">S</span>
          <span className="text-lg font-semibold">SkillSync</span>
        </div>
        <div>
          <h2 className="max-w-md text-2xl font-semibold leading-snug text-foreground">Rank candidates against what the job actually asks for.</h2>
          <p className="mt-2 max-w-md text-base text-muted-foreground">Break a job description into requirements, find the resume passage that proves each one, and rank with weights you control.</p>
          <ul className="mt-8 flex max-w-md flex-col gap-5">
            {POINTS.map(([Icon, head, body]) => (
              <li key={head} className="flex gap-3">
                <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                <div><p className="font-medium text-foreground">{head}</p><p className="text-sm text-muted-foreground">{body}</p></div>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-muted-foreground">Use synthetic or consented resumes only.</p>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center gap-2 lg:hidden">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">S</span>
            <span className="text-base font-semibold">SkillSync</span>
          </div>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">{subtitle}</p>
          {children}
          <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div>
        </div>
      </div>
    </div>
  )
}
