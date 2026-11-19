import { forwardRef, useId } from 'react'
import { cn } from '../../lib/utils.js'

const FIELD = 'w-full rounded-md border border-border-subtle bg-card text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

export const Input = forwardRef(function Input({ className, error, prefix, ...props }, ref) {
  const input = (
    <input ref={ref} aria-invalid={error || undefined}
      className={cn(FIELD, 'h-9 px-3', prefix && 'pl-8', error && 'border-destructive focus-visible:ring-ring-destructive', className)} {...props} />
  )
  if (!prefix) return input
  return (
    <div className="relative flex items-center">
      <span className="pointer-events-none absolute left-2.5 text-muted-foreground [&_svg]:size-4">{prefix}</span>
      {input}
    </div>
  )
})

export const Textarea = forwardRef(function Textarea({ className, error, ...props }, ref) {
  return <textarea ref={ref} className={cn(FIELD, 'min-h-20 resize-y px-3 py-2', error && 'border-destructive', className)} {...props} />
})

export const Select = forwardRef(function Select({ className, children, ...props }, ref) {
  return <select ref={ref} className={cn(FIELD, 'h-9 px-2', className)} {...props}>{children}</select>
})

// Label + control + helper/error text with correct aria wiring.
export function Field({ label, hint, error, children, className }) {
  const id = useId()
  const control = typeof children === 'function' ? children({ id, 'aria-describedby': `${id}-msg` }) : children
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label && <label htmlFor={id} className="text-sm font-medium text-foreground">{label}</label>}
      {control}
      {(error || hint) && <p id={`${id}-msg`} className={cn('text-xs', error ? 'text-destructive-text' : 'text-muted-foreground')}>{error || hint}</p>}
    </div>
  )
}
