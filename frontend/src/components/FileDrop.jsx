import { useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { cn } from '../lib/utils.js'

// Drag and drop, or click / keyboard to choose. Calls onFiles(File[]).
export default function FileDrop({ onFiles, multiple = true, disabled = false, title, hint }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)
  const take = (list) => {
    const files = Array.from(list || [])
    if (files.length) onFiles(multiple ? files : files.slice(0, 1))
  }
  return (
    <div role="button" tabIndex={disabled ? -1 : 0} aria-disabled={disabled}
      onClick={() => !disabled && input.current.click()}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && !disabled && (e.preventDefault(), input.current.click())}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) take(e.dataTransfer.files) }}
      className={cn('flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed border-border px-4 py-8 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        over ? 'border-primary bg-accent' : 'bg-card hover:bg-muted/40', disabled && 'pointer-events-none opacity-50')}>
      <UploadCloud className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium text-foreground">{title || (multiple ? 'Drop PDF or DOCX resumes here, or click to choose' : 'Drop a PDF or DOCX resume here, or click to choose')}</p>
      <p className="text-xs text-muted-foreground">{hint || 'Up to 10 MB per file. Scanned PDFs are read with OCR.'}</p>
      <input ref={input} type="file" hidden multiple={multiple} accept=".pdf,.docx" onChange={(e) => { take(e.target.files); e.target.value = '' }} />
    </div>
  )
}
