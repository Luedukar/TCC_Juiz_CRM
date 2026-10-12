// Cópia local do último quadro carregado: permite exibir algo útil se a API cair
// ou demorar. É apagada no logout (o aparelho pode ser compartilhado).
const PREFIX = 'crm.snapshot.'

export interface Snapshot<T> {
  data: T
  savedAt: number
}

export function readSnapshot<T>(key: string): Snapshot<T> | undefined {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw ? (JSON.parse(raw) as Snapshot<T>) : undefined
  } catch {
    return undefined
  }
}

export function writeSnapshot<T>(key: string, data: T, savedAt: number): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify({ data, savedAt }))
  } catch {
    /* quota cheia ou armazenamento bloqueado: ignora */
  }
}

export function clearSnapshots(): void {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => localStorage.removeItem(k))
  } catch {
    /* ignora */
  }
}
