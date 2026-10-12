import type { Tokens } from './types'
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const STORE = 'vela-crm-session'
let tokens: Tokens | null = (() => { try { return JSON.parse(localStorage.getItem(STORE) || 'null') } catch { return null } })()
let refreshFlight: Promise<boolean> | null = null
export function getSession() { return tokens }
export function saveSession(value: Tokens | null) { tokens = value; value ? localStorage.setItem(STORE, JSON.stringify(value)) : localStorage.removeItem(STORE) }
async function renew() {
  if (!tokens?.refresh_token) return false
  if (refreshFlight) return refreshFlight
  refreshFlight = (async () => {
    try {
      const response = await fetch(`${API}/auth/refresh`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:tokens!.refresh_token}),signal:AbortSignal.timeout(10000)})
      if (!response.ok) { saveSession(null); return false }
      saveSession(await response.json()); return true
    } catch { return false } finally { refreshFlight = null }
  })()
  return refreshFlight
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = () => {
    const method = (init.method || 'GET').toUpperCase()
    return fetch(`${API}${path}`, { ...init, signal: init.signal ?? (method === 'GET' ? AbortSignal.timeout(15000) : undefined), headers: { ...(init.body ? {'Content-Type':'application/json'} : {}), ...(tokens ? {Authorization:`Bearer ${tokens.access_token}`} : {}), ...init.headers } })
  }
  let response: Response
  try { response = await send() } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('A API está demorando para responder. Tente carregar novamente.')
    throw new Error('Não foi possível conectar à API. Verifique a rede e tente novamente.')
  }
  if (response.status === 401 && tokens && path !== '/auth/refresh') {
    if (await renew()) { try { response = await send() } catch { throw new Error('Falha de conexão ao renovar a sessão.') } }
  }
  if (!response.ok) {
    let detail = 'Não foi possível concluir a solicitação.'
    try { const payload = await response.json(); detail = payload.detail || detail } catch { /* resposta sem JSON */ }
    if (response.status === 429) detail = 'Muitas tentativas. Aguarde um pouco antes de tentar novamente.'
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}
export async function signIn(email: string, password: string, workspace_id: number) {
  const result = await api<{access_token:string;refresh_token:string;token_type:string}>('/auth/login', {method:'POST',body:JSON.stringify({email,password,workspace_id})})
  saveSession(result)
  return api<import('./types').User>('/auth/me')
}
export async function signOut() {
  const refresh_token = tokens?.refresh_token
  if (refresh_token) { try { await api('/auth/logout',{method:'POST',body:JSON.stringify({refresh_token})}) } catch { /* remove local credentials even while offline */ } }
  saveSession(null)
}
