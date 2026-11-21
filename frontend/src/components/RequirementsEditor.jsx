import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { Badge, ImportanceBadge, KindBadge, KIND, isScoredKind } from './ui/Badge.jsx'
import { Alert, EmptyState } from './ui/Feedback.jsx'
import { Button } from './ui/Button.jsx'
import { Input, Select } from './ui/Form.jsx'

const DEFAULT_WEIGHT = { must: 3, should: 2, nice: 1 }
const WARN_ABOVE = 15 // more scored requirements than this usually means duties or soft skills slipped in

const WEIGHT_NOTE = {
  default: 'Default weight for this importance',
  manual: 'Weight set by hand',
}

function yearsLabel(m = {}) {
  if (m.years_min == null && m.years_required == null) return null
  const lo = m.years_min ?? m.years_required
  return m.years_max != null ? `${lo} to ${m.years_max} years (needs ${lo})` : `${lo}+ years`
}

function Row({ r, onSave, edit }) {
  const m = r.meta || {}
  const scored = isScoredKind(m.kind)
  const skills = m.skills || []
  return (
    <li className="flex flex-wrap items-start gap-3 px-4 py-3">
      <span className="mt-2 w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{r.idx + 1}</span>
      <div className="min-w-0 flex-1 basis-64">
        {onSave ? <Input value={r.text} onChange={(e) => edit(r.id, 'text', e.target.value)} aria-label={`Requirement ${r.idx + 1}`} /> : <p className="py-1.5 text-sm text-foreground">{r.text}</p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <KindBadge kind={m.kind} />
          {skills.map((s) => <Badge key={s} color="neutral">{s}</Badge>)}
          {skills.length > 1 && <Badge color="accent">{m.skills_mode === 'any' ? 'any one of these' : 'all of these'}</Badge>}
          {yearsLabel(m) && <Badge color="neutral">{yearsLabel(m)}</Badge>}
          {m.degree_level_required != null && <Badge color="neutral">degree level {m.degree_level_required}</Badge>}
          {m.query && m.query !== r.text && <span className="text-xs text-muted-foreground">searched as "{m.query}"</span>}
        </div>
      </div>
      {onSave ? (
        <div className="flex flex-wrap items-center gap-2">
          <Select value={m.kind || 'hard_skill'} onChange={(e) => edit(r.id, 'kind', e.target.value)} className="w-32" aria-label="Kind">
            {Object.entries(KIND).map(([k, [, label]]) => <option key={k} value={k}>{label}</option>)}
          </Select>
          {skills.length > 1 && (
            <Select value={m.skills_mode || 'all'} onChange={(e) => edit(r.id, 'skills_mode', e.target.value)} className="w-24" aria-label="Skills mode">
              <option value="all">All of</option><option value="any">Any of</option>
            </Select>
          )}
          <Select value={r.importance} onChange={(e) => edit(r.id, 'importance', e.target.value)} className="w-24" aria-label="Importance">
            <option value="must">Must</option><option value="should">Should</option><option value="nice">Nice</option>
          </Select>
          <div className="flex flex-col">
            <Input type="number" min="0" step="0.5" value={r.weight} onChange={(e) => edit(r.id, 'weight', e.target.value)} className="w-20 tabular-nums" aria-label="Weight" disabled={!scored} />
            <span className="mt-0.5 text-[11px] leading-tight text-muted-foreground">{scored ? WEIGHT_NOTE[m.weight_source] || WEIGHT_NOTE.default : 'not scored'}</span>
          </div>
        </div>
      ) : <div className="flex items-center gap-2"><ImportanceBadge importance={r.importance} /><span className="text-xs tabular-nums text-muted-foreground">{scored ? `weight ${r.weight}` : 'not scored'}</span></div>}
    </li>
  )
}

// Editable list of requirements (recruiter) or a read-only list (student, when onSave is not given).
// Hard skills, experience and education are scored. Soft skills and duties are listed below, never scored.
export default function RequirementsEditor({ requirements, onSave, saving }) {
  const [rows, setRows] = useState(requirements)
  useEffect(() => setRows(requirements), [requirements])

  const edit = (id, field, value) => setRows((rs) => rs.map((r) => {
    if (r.id !== id) return r
    if (field === 'kind' || field === 'skills_mode') return { ...r, meta: { ...r.meta, [field]: value }, weight: field === 'kind' ? (isScoredKind(value) ? DEFAULT_WEIGHT[r.importance] : 0) : r.weight }
    const next = { ...r, [field]: value }
    if (field === 'importance') next.weight = isScoredKind(r.meta?.kind) ? DEFAULT_WEIGHT[value] : 0 // mirrors the server
    return next
  }))
  const changed = rows.filter((r) => {
    const o = requirements.find((x) => x.id === r.id)
    return o && (o.text !== r.text || o.importance !== r.importance || Number(o.weight) !== Number(r.weight)
      || o.meta?.kind !== r.meta?.kind || o.meta?.skills_mode !== r.meta?.skills_mode)
  })
  const patchFor = (r) => {
    const o = requirements.find((x) => x.id === r.id)
    const p = { id: r.id }
    if (o.text !== r.text) p.text = r.text
    if (o.importance !== r.importance) p.importance = r.importance
    if (o.meta?.kind !== r.meta?.kind) p.kind = r.meta.kind
    if (o.meta?.skills_mode !== r.meta?.skills_mode) p.skills_mode = r.meta.skills_mode
    // a weight is sent only when edited by hand, so the server keeps tracking the default for the importance
    const defaultNow = isScoredKind(r.meta?.kind) ? DEFAULT_WEIGHT[r.importance] : 0
    if (Number(o.weight) !== Number(r.weight) && Number(r.weight) !== defaultNow) p.weight = Number(r.weight)
    return p
  }

  if (!rows.length) return <EmptyState title="No requirements were extracted">Edit the job description and create the job again, or add a clearer Requirements section.</EmptyState>
  const scored = rows.filter((r) => isScoredKind(r.meta?.kind))
  const listed = rows.filter((r) => !isScoredKind(r.meta?.kind))

  return (
    <div>
      {scored.length > WARN_ABOVE && (
        <div className="p-4 pb-0"><Alert color="warning" title={`${scored.length} scored requirements`}>More than {WARN_ABOVE} usually means duties or soft skills were read as requirements. Change their kind to Duty or Soft skill so they are listed but not scored.</Alert></div>
      )}
      <ul className="divide-y divide-border">{scored.map((r) => <Row key={r.id} r={r} onSave={onSave} edit={edit} />)}</ul>
      {listed.length > 0 && (
        <div className="border-t border-border bg-muted/30">
          <p className="px-4 pt-3 text-sm font-medium">Listed, not scored <span className="font-normal text-muted-foreground">({listed.length})</span></p>
          <p className="px-4 pb-1 text-xs text-muted-foreground">Soft skills and duties cannot be checked from a resume, so they never change a score. Change the kind if one of them is a real requirement.</p>
          <ul className="divide-y divide-border">{listed.map((r) => <Row key={r.id} r={r} onSave={onSave} edit={edit} />)}</ul>
        </div>
      )}
      {onSave && (
        <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3">
          <p className="text-xs text-muted-foreground">Changing wording, kind or any-of mode means scoring must be re-run. Changing importance or weight does not.</p>
          <Button leftIcon={<Save />} loading={saving} disabled={!changed.length} onClick={() => onSave(changed.map(patchFor))}>
            Save changes{changed.length ? ` (${changed.length})` : ''}
          </Button>
        </div>
      )}
    </div>
  )
}
