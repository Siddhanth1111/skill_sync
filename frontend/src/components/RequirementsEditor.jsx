import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { Badge, ImportanceBadge } from './ui/Badge.jsx'
import { Button } from './ui/Button.jsx'
import { Input, Select } from './ui/Form.jsx'
import { EmptyState } from './ui/Feedback.jsx'

const DEFAULT_WEIGHT = { must: 3, should: 2, nice: 1 }
const TYPE_COLOR = { skill: 'accent', experience: 'neutral', education: 'neutral' }

// Editable list of requirements (recruiter) or a read-only list (student, when onSave is not given).
export default function RequirementsEditor({ requirements, onSave, saving }) {
  const [rows, setRows] = useState(requirements)
  useEffect(() => setRows(requirements), [requirements])

  const edit = (id, field, value) => setRows((rs) => rs.map((r) => {
    if (r.id !== id) return r
    const next = { ...r, [field]: value }
    if (field === 'importance') next.weight = DEFAULT_WEIGHT[value] // mirrors the server: importance resets the weight
    return next
  }))
  const changed = rows.filter((r) => {
    const o = requirements.find((x) => x.id === r.id)
    return o && (o.text !== r.text || o.importance !== r.importance || Number(o.weight) !== Number(r.weight))
  })

  if (!rows.length) return <EmptyState title="No requirements were extracted">Edit the job description and create the job again, or add a clearer Requirements section.</EmptyState>

  return (
    <div>
      <ul className="divide-y divide-border">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-start gap-3 px-4 py-3">
            <span className="mt-2 w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{r.idx + 1}</span>
            <div className="min-w-0 flex-1 basis-64">
              {onSave ? <Input value={r.text} onChange={(e) => edit(r.id, 'text', e.target.value)} aria-label={`Requirement ${r.idx + 1}`} /> : <p className="py-1.5 text-sm text-foreground">{r.text}</p>}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <Badge color={TYPE_COLOR[r.type]}>{r.type}</Badge>
                {(r.meta?.skills || []).map((s) => <Badge key={s} color="neutral">{s}</Badge>)}
                {r.meta?.years_required != null && <Badge color="neutral">{r.meta.years_required}+ years</Badge>}
                {r.meta?.degree_level_required != null && <Badge color="neutral">degree level {r.meta.degree_level_required}</Badge>}
              </div>
            </div>
            {onSave ? (
              <div className="flex items-center gap-2">
                <Select value={r.importance} onChange={(e) => edit(r.id, 'importance', e.target.value)} className="w-24" aria-label="Importance">
                  <option value="must">Must</option><option value="should">Should</option><option value="nice">Nice</option>
                </Select>
                <Input type="number" min="0" step="0.5" value={r.weight} onChange={(e) => edit(r.id, 'weight', e.target.value)} className="w-20 tabular-nums" aria-label="Weight" />
              </div>
            ) : <div className="flex items-center gap-2"><ImportanceBadge importance={r.importance} /><span className="text-xs tabular-nums text-muted-foreground">weight {r.weight}</span></div>}
          </li>
        ))}
      </ul>
      {onSave && (
        <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3">
          <p className="text-xs text-muted-foreground">Changing a requirement's wording means scoring must be re-run. Changing importance or weight does not.</p>
          <Button leftIcon={<Save />} loading={saving} disabled={!changed.length} onClick={() => onSave(changed.map((r) => ({ id: r.id, text: r.text, importance: r.importance, weight: Number(r.weight) })))}>
            Save changes{changed.length ? ` (${changed.length})` : ''}
          </Button>
        </div>
      )}
    </div>
  )
}
