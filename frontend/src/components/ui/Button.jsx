import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils.js'

// Variants and sizes follow the design system Button. One primary action per screen.
const VARIANTS = {
  primary: 'bg-primary text-primary-foreground font-light hover:bg-primary-hover active:bg-primary-active focus-visible:ring-ring',
  destructive: 'bg-destructive text-destructive-foreground font-light hover:bg-destructive-hover active:bg-destructive-active focus-visible:ring-ring-destructive',
  basic: 'bg-muted text-foreground font-light hover:bg-muted-hover active:bg-muted-active focus-visible:ring-ring',
  outline: 'border border-border bg-transparent text-foreground font-light hover:bg-muted-hover active:bg-muted-active focus-visible:ring-ring',
  transparent: 'bg-transparent text-muted-foreground font-light hover:bg-muted-hover hover:text-foreground active:bg-muted-active focus-visible:ring-ring',
  link: 'bg-transparent text-primary font-normal underline-offset-2 hover:underline hover:text-primary-hover focus-visible:ring-ring',
}
const SIZES = {
  sm: 'h-6 px-1.5 text-sm [&_svg]:size-3',
  default: 'h-8 px-2.5 text-sm [&_svg]:size-4',
  lg: 'h-10 px-3.5 text-base [&_svg]:size-5',
}
const ICON_SIZES = { sm: 'h-6 w-6 p-0 [&_svg]:size-3', default: 'h-8 w-8 p-0 [&_svg]:size-4', lg: 'h-10 w-10 p-0 [&_svg]:size-5' }

export const Button = forwardRef(function Button(
  { variant = 'primary', size = 'default', leftIcon, rightIcon, iconOnly = false, loading = false, selected = false, className, children, disabled, type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md whitespace-nowrap select-none',
        'focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant], iconOnly ? ICON_SIZES[size] : SIZES[size],
        selected && 'border-primary bg-accent text-accent-foreground',
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="animate-spin" aria-hidden /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  )
})
