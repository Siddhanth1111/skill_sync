import { useEffect, useRef } from 'react'

// Calls `fn` every `ms` while `active` is true. `fn` returns a promise; errors are ignored (next tick retries).
export function usePolling(fn, active, ms = 1500) {
  const saved = useRef(fn)
  saved.current = fn
  useEffect(() => {
    if (!active) return undefined
    const id = setInterval(() => saved.current().catch(() => {}), ms)
    return () => clearInterval(id)
  }, [active, ms])
}
