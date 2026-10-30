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
      <p className="note">Pipeline stages 1 to 5 only: upload, text extraction, structuring, requirements, chunking.
        Scoring and ranking are not built yet.</p>
      <main>{mode === 'recruiter' ? <Recruiter /> : <Student />}</main>
    </div>
  )
}
