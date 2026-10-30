// Thin wrapper over the backend. All paths go through the Vite proxy at /api.
const BASE = '/api'

async function request(path, options) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    throw new Error('Cannot reach the backend. Is it running on port 8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {}
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request('/health'),
  listJobs: () => request('/jobs'),
  getJob: (id) => request(`/jobs/${id}`),
  createJob: (title, text) => request('/jobs', json('POST', { title, text })),
  patchRequirements: (id, patches) => request(`/jobs/${id}/requirements`, json('PATCH', patches)),
  uploadResumes: (jobId, files) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request(`/jobs/${jobId}/resumes`, { method: 'POST', body: form })
  },
  jobStatus: (id) => request(`/jobs/${id}/status`),
  getCandidate: (id) => request(`/candidates/${id}`),
  uploadStudentResume: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/student/resume', { method: 'POST', body: form })
  },
}
