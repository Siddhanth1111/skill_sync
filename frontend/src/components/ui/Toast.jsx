import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'
import { cn } from '../../lib/utils.js'

const ToastContext = createContext(null)
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), [])
  const push = useCallback((message, kind = 'success') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, kind }])
    setTimeout(() => dismiss(id), kind === 'error' ? 7000 : 4000)
  }, [dismiss])
  const api = useMemo(() => ({ success: (m) => push(m, 'success'), error: (m) => push(m, 'error') }), [push])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} role="status" className={cn('pointer-events-auto flex items-start gap-2 rounded-lg border bg-card p-3 text-sm shadow-lg', t.kind === 'error' ? 'border-destructive' : 'border-success')}>
            {t.kind === 'error' ? <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />}
            <p className="flex-1 text-foreground">{t.message}</p>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
