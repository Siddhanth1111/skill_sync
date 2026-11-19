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
  listJobs: (mode) => request('/jobs' + (mode ? `?mode=${mode}` : '')),
  getJob: (id) => request(`/jobs/${id}`),
  createJob: (title, text, mode = 'recruiter') => request('/jobs', json('POST', { title, text, mode })),
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
  // Stages 7-12: scoring, matrix, explanation
  startScoring: (jobId) => request(`/jobs/${jobId}/score`, { method: 'POST' }),
  scoringStatus: (jobId) => request(`/jobs/${jobId}/score/status`),
  matrix: (jobId) => request(`/jobs/${jobId}/matrix`),
  ranking: (jobId) => request(`/jobs/${jobId}/ranking`),
  explanation: (candidateId) => request(`/candidates/${candidateId}/explanation`),
  // Stage 13: learning
  rate: (candidateId, rating) => request(`/candidates/${candidateId}/feedback`, json('POST', { rating })),
  model: (jobId) => request(`/jobs/${jobId}/model`),
  trainModel: (jobId) => request(`/jobs/${jobId}/model/train`, { method: 'POST' }),
  // Stage 14: fairness
  auditBlind: (jobId) => request(`/jobs/${jobId}/audit/blind`, { method: 'POST' }),
  auditCounterfactual: (jobId) => request(`/jobs/${jobId}/audit/counterfactual`, { method: 'POST' }),
  auditImpact: (jobId, groups, topN) => request(`/jobs/${jobId}/audit/impact`, json('POST', { groups, top_n: topN })),
  auditWeat: (jobId, groups) => request(`/jobs/${jobId}/audit/weat`, json('POST', { groups })),
  auditHistory: (jobId) => request(`/jobs/${jobId}/audit/history`),
  // Stage 15: student mode
  studentMatch: (candidateId, jobIds) => request('/student/match', json('POST', { candidate_id: candidateId, job_ids: jobIds })),
  studentRoadmap: (candidateId, jobId) => request(`/student/roadmap?candidate_id=${candidateId}&job_id=${jobId}`),
  studentWhatIf: (candidateId, jobId, addition) =>
    request('/student/whatif', json('POST', { candidate_id: candidateId, job_id: jobId, addition })),
}
