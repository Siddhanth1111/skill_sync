import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/utils.js'

export function PageHeader({ title, description, actions, eyebrow, children }) {
  return (
    <div className="px-6 pb-4 pt-5">
      {eyebrow && <p className="mb-0.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</p>}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold leading-tight text-foreground">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

export function StatCard({ label, value, hint, icon: Icon }) {
  return (
    <div className="rounded-lg bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        {Icon && <Icon className="size-4 text-muted-foreground" aria-hidden />}
      </div>
      <p className="mt-2 text-2xl font-medium leading-none tabular-nums text-foreground">{value}</p>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

// Route-driven tabs: each tab is a NavLink so the URL says which tab is open and the back button works.
export function TabNav({ tabs }) {
  return (
    <nav className="flex gap-0 border-b border-border px-6" aria-label="Sections">
      {tabs.map(({ to, label, end, badge }) => (
        <NavLink key={to} to={to} end={end}
          className={({ isActive }) => cn('-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium',
            isActive ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground')}>
          {label}
          {badge != null && <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-muted px-1.5 text-xs text-muted-foreground">{badge}</span>}
        </NavLink>
      ))}
    </nav>
  )
}

export function DataTable({ columns, rows, rowKey, onRowClick, selectedKey, empty, dense = true }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            {columns.map((c) => (
              <th key={c.key} className={cn('whitespace-nowrap bg-muted/40 px-4 font-medium text-muted-foreground', dense ? 'py-2' : 'py-3', c.align === 'right' && 'text-right', c.className)} style={c.width ? { width: c.width } : undefined}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => {
            const key = rowKey(row)
            return (
              <tr key={key} onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(onRowClick && 'cursor-pointer', 'hover:bg-muted/40', selectedKey === key && 'bg-accent hover:bg-accent')}>
                {columns.map((c) => (
                  <td key={c.key} className={cn('px-4 align-middle', dense ? 'py-2' : 'py-3', c.align === 'right' && 'text-right tabular-nums', c.className)}>{c.render ? c.render(row) : row[c.key]}</td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {rows.length === 0 && empty}
    </div>
  )
}
