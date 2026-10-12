export function formatMoney(value: string | number, currency = 'BRL'): string {
  const n = Number(value)
  try {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
  } catch {
    return String(n)
  }
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

const rtf = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' })

/** "há 2 horas", "amanhã", "em 3 dias"... */
export function relativeTime(iso: string, now = Date.now()): string {
  const diffSeconds = Math.round((new Date(iso).getTime() - now) / 1000)
  const abs = Math.abs(diffSeconds)
  if (abs < 60) return rtf.format(diffSeconds, 'second')
  if (abs < 3600) return rtf.format(Math.round(diffSeconds / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour')
  return rtf.format(Math.round(diffSeconds / 86400), 'day')
}

const pad = (n: number) => String(n).padStart(2, '0')

/** ISO -> valor de <input type="datetime-local"> no fuso local. */
export function toLocalInput(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Valor de datetime-local -> ISO com fuso (o backend exige data/hora com timezone). */
export function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}
