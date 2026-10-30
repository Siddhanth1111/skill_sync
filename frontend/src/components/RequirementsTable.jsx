import { useEffect, useState } from 'react'

const DEFAULT_WEIGHT = { must: 3, should: 2, nice: 1 }

// Shows the extracted requirements. With `onSave` it is editable (recruiter); without, read-only (student).
export default function RequirementsTable({ requirements, onSave }) {
  const [rows, setRows] = useState(requirements)
  useEffect(() => setRows(requirements), [requirements])

  const edit = (id, field, value) =>
    setRows((rs) =>
      rs.map((r) => {
        if (r.id !== id) return r
        const next = { ...r, [field]: value }
        if (field === 'importance') next.weight = DEFAULT_WEIGHT[value] // mirrors backend behaviour
        return next
      }),
    )

  const changed = rows.filter((r) => {
    const o = requirements.find((x) => x.id === r.id)
    return o && (o.text !== r.text || o.importance !== r.importance || Number(o.weight) !== Number(r.weight))
  })

  const save = () =>
    onSave(changed.map((r) => ({ id: r.id, text: r.text, importance: r.importance, weight: Number(r.weight) })))

  if (!rows.length) return <p className="muted">No requirements were extracted.</p>

  return (
    <div>
      <table>
        <thead>
          <tr><th>#</th><th>Requirement</th><th>Type</th><th>Importance</th><th>Weight</th><th>Details</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.idx + 1}</td>
              <td>
                {onSave ? (
                  <input value={r.text} onChange={(e) => edit(r.id, 'text', e.target.value)} />
                ) : (
                  r.text
                )}
              </td>
              <td><span className={'tag ' + r.type}>{r.type}</span></td>
              <td>
                {onSave ? (
                  <select value={r.importance} onChange={(e) => edit(r.id, 'importance', e.target.value)}>
                    <option value="must">must</option>
                    <option value="should">should</option>
                    <option value="nice">nice</option>
                  </select>
                ) : (
                  <span className={'tag ' + r.importance}>{r.importance}</span>
                )}
              </td>
              <td>
                {onSave ? (
                  <input className="num" type="number" min="0" step="0.5" value={r.weight}
                    onChange={(e) => edit(r.id, 'weight', e.target.value)} />
                ) : (
                  r.weight
                )}
              </td>
              <td className="small">
                {(r.meta?.skills || []).join(', ')}
                {r.meta?.years_required != null && ` | ${r.meta.years_required}+ yrs`}
                {r.meta?.degree_level_required != null && ` | degree level ${r.meta.degree_level_required}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {onSave && (
        <button className="primary" disabled={!changed.length} onClick={save}>
          Save changes{changed.length ? ` (${changed.length})` : ''}
        </button>
      )}
    </div>
  )
}
