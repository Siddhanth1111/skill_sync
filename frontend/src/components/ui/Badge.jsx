import { cn } from '../../lib/utils.js'

const BG = { accent: 'bg-accent', neutral: 'bg-muted', destructive: 'bg-destructive-light', success: 'bg-success-light', warning: 'bg-warning-light', alert: 'bg-alert-light' }
const TEXT = { accent: 'text-accent-foreground', neutral: 'text-muted-foreground', destructive: 'text-destructive-text', success: 'text-success-text', warning: 'text-warning-text', alert: 'text-alert-text' }
const DOT = { accent: 'bg-primary', neutral: 'bg-muted-foreground', destructive: 'bg-destructive', success: 'bg-success', warning: 'bg-warning', alert: 'bg-alert' }

export function Badge({ children, color = 'neutral', dot = false, className }) {
  return (
    <span className={cn('inline-flex w-fit shrink-0 items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium whitespace-nowrap', BG[color], TEXT[color], className)}>
      {dot && <span className={cn('size-1.5 shrink-0 rounded-full', DOT[color])} aria-hidden />}
      {children}
    </span>
  )
}

// Domain mappings used across the product.
export const STATUS = { met: ['success', 'Met'], partial: ['warning', 'Partial'], not_met: ['destructive', 'Not met'] }
export const IMPORTANCE = { must: ['accent', 'Must'], should: ['neutral', 'Should'], nice: ['neutral', 'Nice'] }
export const FILE_STATUS = { queued: ['neutral', 'Queued'], parsing: ['warning', 'Parsing'], done: ['success', 'Done'], failed: ['destructive', 'Failed'] }

export const StatusBadge = ({ status }) => <Badge color={STATUS[status][0]} dot>{STATUS[status][1]}</Badge>
export const ImportanceBadge = ({ importance }) => <Badge color={IMPORTANCE[importance][0]}>{IMPORTANCE[importance][1]}</Badge>
export const FileStatusBadge = ({ status }) => <Badge color={FILE_STATUS[status][0]} dot>{FILE_STATUS[status][1]}</Badge>
export const SourceBadge = ({ source, label }) => (
  <Badge color={source === 'llm' ? 'accent' : 'neutral'}>{label || (source === 'llm' ? 'Language model' : 'Rules')}</Badge>
)
