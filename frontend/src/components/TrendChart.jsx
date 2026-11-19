// Tiny dependency-free line chart of one audit kind's headline value over runs (monitoring over time).
export default function TrendChart({ points, label }) {
  const vals = points.map((p) => p.value).filter((v) => v != null)
  if (vals.length === 0) return null
  const w = 320, h = 90, pad = 14
  const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0.0001)
  const x = (i) => pad + (points.length === 1 ? (w - 2 * pad) / 2 : (i * (w - 2 * pad)) / (points.length - 1))
  const y = (v) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad)
  const path = points.map((p, i) => (p.value == null ? null : `${x(i)},${y(p.value)}`)).filter(Boolean).join(' ')
  return (
    <figure className="trend">
      <figcaption className="small">{label}</figcaption>
      <svg width={w} height={h} role="img" aria-label={`trend of ${label}`}>
        <line x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} stroke="#dde1e7" />
        <polyline fill="none" stroke="#3b5bdb" strokeWidth="2" points={path} />
        {points.map((p, i) => p.value != null && <circle key={i} cx={x(i)} cy={y(p.value)} r="3.5" fill="#3b5bdb"><title>{`run ${p.id}: ${p.value.toFixed(3)}`}</title></circle>)}
      </svg>
    </figure>
  )
}
