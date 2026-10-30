import { useState } from 'react'

const SECTION_ORDER = ['header', 'summary', 'experience', 'education', 'skills', 'projects', 'certifications', 'achievements']

// Everything Stages 2 to 5 produced for one resume.
export default function CandidateView({ candidate: c }) {
  const [showRaw, setShowRaw] = useState(false)
  if (c.status === 'failed') return <p className="error">Failed: {c.error}</p>
  if (c.status !== 'done') return <p className="muted">Status: {c.status}...</p>

  const p = c.profile || {}
  const conf = c.parse_confidence || {}
  const bySection = {}
  c.chunks.forEach((ch) => (bySection[ch.section] ||= []).push(ch))
  const sections = Object.keys(bySection).sort((a, b) => SECTION_ORDER.indexOf(a) - SECTION_ORDER.indexOf(b))

  return (
    <div className="candidate">
      <div className="row">
        <h3>{p.name || c.filename}</h3>
        <span className={'tag ' + (c.source === 'llm' ? 'llm' : 'rules')}>extracted by {c.source}</span>
        {c.needs_ocr && <span className="tag warn">OCR used</span>}
      </div>

      {conf.low && (
        <div className="warning">
          Low parse confidence: {(conf.reasons || []).join(', ')}.
          <span className="small"> ({conf.char_count} characters, {conf.sections_detected} sections detected)</span>
        </div>
      )}
      {(p.warnings || []).map((w, i) => <div key={i} className="warning">{w}</div>)}

      <h4>Profile</h4>
      <dl>
        <dt>Email</dt><dd>{p.email || '-'}</dd>
        <dt>Phone</dt><dd>{p.phone || '-'}</dd>
        <dt>Years of experience</dt><dd>{p.years_experience} <span className="small">(computed from role dates, overlaps merged)</span></dd>
        <dt>Education level</dt><dd>{p.education_level} <span className="small">(0 none, 1 bachelor, 2 master, 3 PhD)</span></dd>
      </dl>
      <div className="chips">{(p.skills || []).map((s) => <span key={s} className="chip">{s}</span>)}</div>

      <h4>Roles</h4>
      {p.roles?.length ? (
        <table><thead><tr><th>Title</th><th>Company</th><th>Start</th><th>End</th></tr></thead>
          <tbody>{p.roles.map((r, i) => <tr key={i}><td>{r.title}</td><td>{r.company || '-'}</td><td>{r.start || '-'}</td><td>{r.end || '-'}</td></tr>)}</tbody>
        </table>
      ) : <p className="muted">None found.</p>}

      <h4>Education</h4>
      {p.education?.length ? (
        <table><thead><tr><th>Degree</th><th>Institution</th><th>Level</th><th>Year</th></tr></thead>
          <tbody>{p.education.map((e, i) => <tr key={i}><td>{e.degree}</td><td>{e.institution || '-'}</td><td>{e.level}</td><td>{e.year || '-'}</td></tr>)}</tbody>
        </table>
      ) : <p className="muted">None found.</p>}

      <h4>Chunks <span className="small">({c.chunks.length} segments, at most 500 characters, labelled by section)</span></h4>
      {sections.map((s) => (
        <div key={s} className="section">
          <div className="section-name">{s} <span className="small">({bySection[s].length})</span></div>
          {bySection[s].map((ch) => (
            <pre key={ch.id} className="chunk"><span className="small">#{ch.idx} · {ch.text.length} chars{'\n'}</span>{ch.text}</pre>
          ))}
        </div>
      ))}

      <button onClick={() => setShowRaw(!showRaw)}>{showRaw ? 'Hide' : 'Show'} extracted text</button>
      {showRaw && <pre className="chunk raw">{c.raw_text}</pre>}
    </div>
  )
}
