import { useRef, useState } from 'react'

// Drag-and-drop or click to pick files. Calls onFiles(File[]).
export default function FileDrop({ onFiles, multiple = true, disabled = false, label }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)
  const handle = (list) => {
    const files = Array.from(list || [])
    if (files.length) onFiles(multiple ? files : files.slice(0, 1))
  }
  return (
    <div
      className={'drop' + (over ? ' over' : '') + (disabled ? ' disabled' : '')}
      onClick={() => !disabled && input.current.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) handle(e.dataTransfer.files) }}
    >
      {label || 'Drop PDF or DOCX files here, or click to choose'}
      <input ref={input} type="file" hidden multiple={multiple} accept=".pdf,.docx"
        onChange={(e) => { handle(e.target.files); e.target.value = '' }} />
    </div>
  )
}
