import { api } from '../../api/index.js'
import { useApi, usePolling } from '../../api/hooks.js'

// The student's current resume (latest upload), or null. Polls while it is still being parsed.
export function useResume() {
  const r = useApi(async () => {
    const s = await api.studentResume() // null until the first upload
    return s && s.status === 'done' ? await api.candidate(s.id) : s
  })
  const parsing = r.data && (r.data.status === 'queued' || r.data.status === 'parsing')
  usePolling(() => r.reload(true), !!parsing, 1500)
  return r
}
