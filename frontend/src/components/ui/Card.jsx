import { cn } from '../../lib/utils.js'

// Cards sit on the grey canvas: bg-card, rounded-lg, shadow-sm (design system landing/grid surfaces).
export function Card({ className, children, ...props }) {
  return <section className={cn('rounded-lg bg-card shadow-sm', className)} {...props}>{children}</section>
}

export function CardHeader({ title, description, actions, className }) {
  return (
    <div className={cn('flex items-start justify-between gap-4 border-b border-border px-4 py-3', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-medium text-foreground">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export const CardBody = ({ className, children }) => <div className={cn('p-4', className)}>{children}</div>
