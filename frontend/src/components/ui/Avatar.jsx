import { cn } from '../../lib/utils.js'
import { initials } from '../../lib/utils.js'

export const Avatar = ({ name, size = 'default', className }) => (
  <span className={cn('inline-flex shrink-0 items-center justify-center rounded-full bg-muted font-semibold text-muted-foreground', size === 'sm' ? 'size-6 text-xs' : 'size-8 text-xs', className)} aria-hidden>
    {initials(name)}
  </span>
)
