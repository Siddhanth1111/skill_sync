import { useEffect, useState } from 'react'
import { api } from './api.js'
import Recruiter from './pages/Recruiter.jsx'
import Student from './pages/Student.jsx'

export default function App() {
  const [mode, setMode] = useState('recruiter')
  const [backendUp, setBackendUp] = useState(null)

  useEffect(() => {
    api.health().then(() => setBackendUp(true)).catch(() => setBackendUp(false))
  }, [])

  return (
    <div className="app">
      <header>
        <h1>SkillSync</h1>
        <nav>
          <button className={mode === 'recruiter' ? 'tab active' : 'tab'} onClick={() => setMode('recruiter')}>
            Recruiter
          </button>
          <button className={mode === 'student' ? 'tab active' : 'tab'} onClick={() => setMode('student')}>
            Student
          </button>
        </nav>
        <span className={'pill ' + (backendUp ? 'ok' : backendUp === false ? 'bad' : '')}>
          {backendUp ? 'backend connected' : backendUp === false ? 'backend offline' : 'checking...'}
        </span>
      </header>
      <p className="note">Pipeline stages 1 to 15: upload and parsing, requirements, embeddings and retrieval, reranking, verified
        evidence, scoring and ranking, explanations, learning from ratings, fairness audits, and student mode. A person makes
        every hiring decision.</p>
      <main>{mode === 'recruiter' ? <Recruiter /> : <Student />}</main>
    </div>
  )
}
