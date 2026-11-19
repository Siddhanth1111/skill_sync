import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils.js'
import { Button } from './Button.jsx'

function useEscape(onClose, open) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
}

function useFocusOnOpen(open) {
  const ref = useRef(null)
  useEffect(() => { if (open) ref.current?.focus() }, [open])
  return ref
}

export function Dialog({ open, onClose, title, description, children, footer, className }) {
  useEscape(onClose, open)
  const ref = useFocusOnOpen(open)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={cn('w-full max-w-md rounded-lg bg-card shadow-md outline-none', className)}>
        <div className="px-4 pt-4">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {children && <div className="px-4 py-3">{children}</div>}
        {footer && <div className="flex justify-end gap-2 border-t border-border px-4 py-3">{footer}</div>}
      </div>
    </div>
  )
}

// Right-hand panel for evidence and parsed resumes.
export function Sheet({ open, onClose, title, subtitle, children, width = 'max-w-xl' }) {
  useEscape(onClose, open)
  const ref = useFocusOnOpen(open)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={cn('flex h-full w-full flex-col bg-card shadow-md outline-none', width)}>
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-foreground">{title}</h2>
            {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
          </div>
          <Button variant="transparent" iconOnly onClick={onClose} aria-label="Close"><X /></Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  )
}
