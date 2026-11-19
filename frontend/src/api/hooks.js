import { useCallback, useEffect, useRef, useState } from 'react'

// Load data on mount / when deps change. Returns {data, error, loading, reload, setData}.
export function useApi(fn, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])

  const run = useCallback(async (silent = false) => {
    if (!silent) setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fnRef.current()
      if (alive.current) setState({ data, error: null, loading: false })
      return data
    } catch (error) {
      if (alive.current) setState((s) => ({ data: silent ? s.data : null, error, loading: false }))
      return null
    }
  }, [])

  useEffect(() => { if (enabled) run() }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, reload: run, setData: (data) => setState((s) => ({ ...s, data })) }
}

// Call `fn` every `ms` while `active` is true.
export function usePolling(fn, active, ms = 1500) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!active) return undefined
    const id = setInterval(() => Promise.resolve(ref.current()).catch(() => {}), ms)
    return () => clearInterval(id)
  }, [active, ms])
}
