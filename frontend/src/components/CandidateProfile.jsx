import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Badge, SourceBadge } from './ui/Badge.jsx'
import { Alert } from './ui/Feedback.jsx'
import { Button } from './ui/Button.jsx'

const ORDER = ['header', 'summary', 'experience', 'education', 'skills', 'projects', 'certifications', 'achievements']
const LEVELS = ['None or other', 'Bachelor', 'Master', 'PhD']

function Row({ k, children }) {
  return <div className="grid grid-cols-[10rem_1fr] gap-2 py-1.5"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 break-words">{children || '-'}</dd></div>
}

function MiniTable({ head, rows, empty }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm">
        <thead><tr className="bg-muted/40 text-left">{head.map((h) => <th key={h} className="px-3 py-1.5 font-medium text-muted-foreground">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-border">{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="px-3 py-1.5">{c || '-'}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function Section({ title, count, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-border first:border-t-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-1.5 py-2 text-left text-sm font-medium capitalize hover:text-primary" aria-expanded={open}>
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}{title} <span className="font-normal text-muted-foreground">({count})</span>
      </button>
      {open && <div className="pb-2">{children}</div>}
    </div>
  )
}

// Everything Stages 2 to 6 produced for one resume.
export default function CandidateProfile({ candidate: c }) {
  const [raw, setRaw] = useState(false)
  if (c.status === 'failed') return <Alert color="destructive" title="This resume could not be read">{c.error}</Alert>
  if (c.status !== 'done') return <p className="text-sm text-muted-foreground">Status: {c.status}. This page updates when parsing finishes.</p>

  const p = c.profile || {}
  const conf = c.parse_confidence || {}
  const bySection = {}
  c.chunks.forEach((ch) => (bySection[ch.section] ||= []).push(ch))
  const sections = Object.keys(bySection).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <SourceBadge source={c.source} label={c.source === 'llm' ? 'Read by language model' : 'Read by rules'} />
        {c.needs_ocr && <Badge color="warning">OCR used{conf.ocr_confidence != null ? ` (confidence ${Math.round(conf.ocr_confidence)} of 100)` : ''}</Badge>}
        <span className="text-xs text-muted-foreground">{c.filename}</span>
      </div>
      {conf.low && (
        <Alert color="warning" title="Low parse confidence">
          {(conf.reasons || []).join(', ')}. {conf.char_count} characters, {conf.sections_detected} sections detected. Check the extracted text before relying on this profile.
        </Alert>
      )}
      {(p.warnings || []).map((w, i) => <Alert key={i} color="warning">{w}</Alert>)}

      <section>
        <h3 className="mb-1 text-sm font-medium">Profile</h3>
        <dl className="divide-y divide-border text-sm">
          <Row k="Name">{p.name}</Row><Row k="Email">{p.email}</Row><Row k="Phone">{p.phone}</Row>
          <Row k="Experience">{p.years_experience != null && `${p.years_experience} years`} <span className="text-xs text-muted-foreground">computed from role dates, overlaps merged</span></Row>
          <Row k="Education level">{LEVELS[p.education_level] ?? p.education_level}</Row>
          {p.skill_years && Object.keys(p.skill_years).length > 0 && (
            <Row k="Years with a skill">{Object.entries(p.skill_years).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k, y]) => `${k} ${y}`).join(', ')} <span className="text-xs text-muted-foreground">from dated roles that mention it</span></Row>
          )}
        </dl>
        {p.skills?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{p.skills.map((s) => <Badge key={s} color="accent">{s}</Badge>)}</div>}
      </section>

      <section><h3 className="mb-1 text-sm font-medium">Roles</h3>
        <MiniTable head={['Title', 'Company', 'Start', 'End']} rows={(p.roles || []).map((r) => [r.title, r.company, r.start, r.end])} empty="No roles found." /></section>
      <section><h3 className="mb-1 text-sm font-medium">Education</h3>
        <MiniTable head={['Degree', 'Institution', 'Level', 'Year']} rows={(p.education || []).map((e) => [e.degree, e.institution, LEVELS[e.level], e.year])} empty="No education found." /></section>

      <section>
        <h3 className="mb-1 text-sm font-medium">Evidence units <span className="font-normal text-muted-foreground">({c.chunks.length}: one bullet or sentence each, with its role as context. Name, contact details and schools are left out)</span></h3>
        <div>
          {sections.map((s, i) => (
            <Section key={s} title={s} count={bySection[s].length} defaultOpen={i === 0}>
              <div className="flex flex-col gap-1.5">
                {bySection[s].map((ch) => (
                  <div key={ch.id} className="rounded-md border border-border bg-muted/40 p-2">
                    {ch.context && ch.context !== s.charAt(0).toUpperCase() + s.slice(1) && <p className="mb-1 text-[11px] text-muted-foreground">{ch.context}</p>}
                    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">{ch.text}</pre>
                  </div>
                ))}
              </div>
            </Section>
          ))}
        </div>
      </section>

      <div>
        <Button variant="outline" size="sm" onClick={() => setRaw(!raw)}>{raw ? 'Hide' : 'Show'} extracted text</Button>
        {raw && <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{c.raw_text}</pre>}
      </div>
    </div>
  )
}
