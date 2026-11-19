import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { cn } from '../../lib/utils.js'

const ALERT = {
  accent: ['bg-accent border-primary text-accent-foreground', Info, 'text-primary'],
  destructive: ['bg-destructive-light border-destructive text-destructive-text', AlertCircle, 'text-destructive'],
  success: ['bg-success-light border-success text-success-text', CheckCircle2, 'text-success'],
  warning: ['bg-warning-light border-warning text-warning-text', AlertTriangle, 'text-warning'],
}

export function Alert({ color = 'accent', title, children, onDismiss, className, action }) {
  const [cls, Icon, iconCls] = ALERT[color]
  return (
    <div role="alert" className={cn('flex items-start gap-3 rounded-lg border p-3', cls, className)}>
      <Icon className={cn('mt-0.5 size-4 shrink-0', iconCls)} aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={title ? 'mt-0.5' : ''}>{children}</div>}
      </div>
      {action}
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss" className="shrink-0 rounded-sm p-0.5 hover:bg-muted-hover"><X className="size-4" /></button>
      )}
    </div>
  )
}

export const Spinner = ({ className }) => <Loader2 className={cn('size-4 animate-spin text-muted-foreground', className)} aria-label="Loading" />

export const Skeleton = ({ className }) => <div className={cn('rounded-md bg-muted', className)} aria-hidden />

export function Progress({ value, max = 100, className, label }) {
  const p = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)} role="progressbar" aria-label={label} aria-valuenow={Math.round(p)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out" style={{ width: `${p}%` }} />
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children, action, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 px-4 py-12 text-center', className)}>
      {Icon && <Icon className="size-8 text-muted-foreground" aria-hidden />}
      <p className="text-base font-medium text-foreground">{title}</p>
      {children && <p className="max-w-sm text-sm text-muted-foreground">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <Alert color="destructive" title="Unable to load this page" action={onRetry && <button onClick={onRetry} className="text-sm underline underline-offset-2">Retry</button>}>
      {error?.message}
    </Alert>
  )
}

export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="flex flex-col gap-3 p-4" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-8 w-full" />)}
    </div>
  )
}
