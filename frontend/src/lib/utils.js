import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs) => twMerge(clsx(inputs))

export const pct = (v, d = 0) => (v == null ? '-' : (v * 100).toFixed(d))
export const num = (v, d = 1) => (v == null ? '-' : Number(v).toFixed(d))

export function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z') // the API sends UTC without a zone
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}
export function formatDateTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
export const initials = (name) =>
  (name || '?').split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('')
