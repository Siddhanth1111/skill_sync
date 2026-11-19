import { cn } from '../../lib/utils.js'

// Score bar: 0..1 value as a thin bar with the number beside it.
export function ScoreBar({ value, className, tone = 'primary' }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${(value * 100).toFixed(0)} out of 100`}>
        <div className={cn('h-full rounded-full', tone === 'success' ? 'bg-success' : 'bg-primary')} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
      <span className="w-9 text-right text-sm tabular-nums text-foreground">{(value * 100).toFixed(0)}</span>
    </div>
  )
}

// Vertical bars with labels. data: [{label, value, title?}]
export function BarChart({ data, height = 120, className }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <div className={cn('flex items-end justify-start gap-3', className)} style={{ height }} role="img" aria-label="Bar chart">
      {data.map((d) => (
        <div key={d.label} className="flex h-full min-w-0 max-w-16 flex-1 flex-col items-center justify-end gap-1" title={d.title}>
          <span className="text-xs tabular-nums text-muted-foreground">{d.value || ''}</span>
          <div className="w-full rounded-t-sm bg-primary" style={{ height: `${(d.value / max) * 100}%`, minHeight: d.value ? 2 : 0 }} />
          <span className="text-xs text-muted-foreground">{d.label}</span>
        </div>
      ))}
    </div>
  )
}

// A single stacked horizontal bar. parts: [{label, value, tone}]
export function StackedBar({ parts }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1
  const tones = { success: 'bg-success', warning: 'bg-warning', destructive: 'bg-destructive', primary: 'bg-primary', muted: 'bg-muted-foreground' }
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-muted">
        {parts.map((p) => p.value > 0 && <div key={p.label} className={tones[p.tone]} style={{ width: `${(p.value / total) * 100}%` }} title={`${p.label}: ${p.value}`} />)}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={cn('size-2 rounded-full', tones[p.tone])} />{p.label} <span className="tabular-nums text-foreground">{p.value}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

// Line chart of values over runs (monitoring over time).
export function TrendChart({ points, label }) {
  const vals = points.map((p) => p.value).filter((v) => v != null)
  if (!vals.length) return null
  const w = 280, h = 80, pad = 12
  const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0.0001)
  const x = (i) => pad + (points.length === 1 ? (w - 2 * pad) / 2 : (i * (w - 2 * pad)) / (points.length - 1))
  const y = (v) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad)
  const path = points.map((p, i) => (p.value == null ? null : `${x(i)},${y(p.value)}`)).filter(Boolean).join(' ')
  return (
    <figure className="rounded-lg border border-border p-3">
      <figcaption className="mb-1 text-xs text-muted-foreground">{label}</figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label={`Trend of ${label}`}>
        <line x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} className="stroke-border" />
        <polyline fill="none" className="stroke-primary" strokeWidth="2" points={path} />
        {points.map((p, i) => p.value != null && <circle key={p.id} cx={x(i)} cy={y(p.value)} r="3.5" className="fill-primary"><title>{`Run ${p.id}: ${p.value.toFixed(3)}`}</title></circle>)}
      </svg>
    </figure>
  )
}
