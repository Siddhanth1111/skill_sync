// All HTTP goes through here: adds the bearer token, turns API errors into readable messages, and signs the
// user out when the session has expired.
const BASE = '/api'
const TOKEN_KEY = 'skillsync.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function describe(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: [...], msg: '...'}]
    return detail.map((d) => `${(d.loc || []).filter((x) => x !== 'body').join(' ')}: ${d.msg}`.replace(/^: /, '')).join('. ')
  }
  return fallback
}

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

export async function request(path, { method = 'GET', json, form, raw = false, auth = true } = {}) {
  const headers = {}
  const token = tokenStore.get()
  if (auth && token) headers.Authorization = `Bearer ${token}`
  let body
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(json) }
  if (form) body = form
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body })
  } catch {
    throw new ApiError('Cannot reach the server. Check that the backend is running on port 8000.', 0)
  }
  if (!res.ok) {
    let detail
    try { detail = (await res.json()).detail } catch { /* not JSON */ }
    if (res.status === 401 && auth) onUnauthorized()
    throw new ApiError(describe(detail, `Request failed (${res.status}).`), res.status)
  }
  if (res.status === 204) return null
  return raw ? res : res.json()
}
