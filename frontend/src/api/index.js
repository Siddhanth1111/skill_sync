import { request } from './client.js'

const form = (key, files) => {
  const f = new FormData()
  ;[].concat(files).forEach((file) => f.append(key, file))
  return f
}

export const api = {
  // auth
  register: (b) => request('/auth/register', { method: 'POST', json: b, auth: false }),
  login: (b) => request('/auth/login', { method: 'POST', json: b, auth: false }),
  me: () => request('/auth/me'),
  deleteMyData: (deleteAccount) => request(`/me/data?delete_account=${deleteAccount}`, { method: 'DELETE' }),
  health: () => request('/health', { auth: false }),

  // jobs, requirements, resumes (stages 1 to 5)
  jobs: () => request('/jobs'),
  job: (id) => request(`/jobs/${id}`),
  createJob: (title, text) => request('/jobs', { method: 'POST', json: { title, text } }),
  deleteJob: (id) => request(`/jobs/${id}`, { method: 'DELETE' }),
  patchRequirements: (id, patches) => request(`/jobs/${id}/requirements`, { method: 'PATCH', json: patches }),
  uploadResumes: (id, files) => request(`/jobs/${id}/resumes`, { method: 'POST', form: form('files', files) }),
  jobStatus: (id) => request(`/jobs/${id}/status`),
  candidate: (id) => request(`/candidates/${id}`),
  deleteCandidate: (id) => request(`/candidates/${id}`, { method: 'DELETE' }),

  // scoring, ranking, explanation (stages 6 to 12)
  startScoring: (id) => request(`/jobs/${id}/score`, { method: 'POST' }),
  scoringStatus: (id) => request(`/jobs/${id}/score/status`),
  matrix: (id) => request(`/jobs/${id}/matrix`),
  ranking: (id) => request(`/jobs/${id}/ranking`),
  explanation: (cid) => request(`/candidates/${cid}/explanation`),
  exportCsv: async (id) => (await request(`/jobs/${id}/export.csv`, { raw: true })).blob(),

  // learning (13)
  rate: (cid, rating) => request(`/candidates/${cid}/feedback`, { method: 'POST', json: { rating } }),
  model: (id) => request(`/jobs/${id}/model`),
  trainModel: (id) => request(`/jobs/${id}/model/train`, { method: 'POST' }),

  // fairness (14)
  audit: (id, kind, body) => request(`/jobs/${id}/audit/${kind}`, { method: 'POST', json: body }),
  auditHistory: (id) => request(`/jobs/${id}/audit/history`),
  auditDetail: (id, aid) => request(`/jobs/${id}/audit/${aid}`),

  // analytics and search
  jobAnalytics: (id) => request(`/jobs/${id}/analytics`),
  overview: () => request('/analytics/overview'),
  search: (q, jobId) => request(`/search?q=${encodeURIComponent(q)}${jobId ? `&job_id=${jobId}` : ''}`),

  // student mode (15)
  studentResume: () => request('/student/resume'),
  uploadStudentResume: (file) => request('/student/resume', { method: 'POST', form: form('file', file) }),
  studentMatch: (candidate_id, job_ids) => request('/student/match', { method: 'POST', json: { candidate_id, job_ids } }),
  studentMatches: () => request('/student/matches'),
  roadmap: (cid, jid) => request(`/student/roadmap?candidate_id=${cid}&job_id=${jid}`),
  whatIf: (candidate_id, job_id, addition) => request('/student/whatif', { method: 'POST', json: { candidate_id, job_id, addition } }),

  // admin
  adminStats: () => request('/admin/stats'),
  adminUsers: () => request('/admin/users'),
  adminActivity: (action) => request(`/admin/activity?limit=200${action ? `&action=${action}` : ''}`),
  adminDeleteUser: (id) => request(`/admin/users/${id}`, { method: 'DELETE' }),
}
