import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, onAuthLost, refreshSession, tokenStore } from '../lib/api'
import { clearSnapshots } from '../lib/snapshot'
import type { LoginResponse, User } from '../lib/types'

type Status = 'loading' | 'authenticated' | 'anonymous' | 'unreachable'

interface AuthState {
  user: User | null
  status: Status
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  reloadUser: () => Promise<void>
  retryBootstrap: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [attempt, setAttempt] = useState(0)

  const clearSession = useCallback(() => {
    tokenStore.clear()
    clearSnapshots()
    qc.clear()
    setUser(null)
    setStatus('anonymous')
  }, [qc])

  // Sessão perdida em qualquer chamada (refresh rejeitado) leva de volta ao login.
  useEffect(() => {
    onAuthLost(clearSession)
    return () => onAuthLost(null)
  }, [clearSession])

  // Restaura a sessão ao carregar a página.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      setStatus('loading')
      const result = await refreshSession()
      if (cancelled) return
      if (result === 'no_token' || result === 'rejected') {
        setStatus('anonymous')
        return
      }
      if (result === 'unreachable') {
        setStatus('unreachable')
        return
      }
      try {
        const me = await api<User>('/auth/me')
        if (!cancelled) {
          setUser(me)
          setStatus('authenticated')
        }
      } catch (error) {
        if (cancelled) return
        setStatus(error instanceof ApiError && error.isConnectivity ? 'unreachable' : 'anonymous')
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [attempt])

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<LoginResponse>('/auth/login', { method: 'POST', body: { email, password }, auth: false })
    tokenStore.set(data)
    setUser(data.user)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh()
    if (refresh) {
      try {
        await api<void>('/auth/logout', { method: 'POST', body: { refresh_token: refresh }, auth: false, timeoutMs: 4000 })
      } catch {
        /* encerra localmente mesmo se a API não responder */
      }
    }
    clearSession()
  }, [clearSession])

  const reloadUser = useCallback(async () => {
    setUser(await api<User>('/auth/me'))
  }, [])

  const retryBootstrap = useCallback(() => setAttempt((n) => n + 1), [])

  const value = useMemo(
    () => ({ user, status, login, logout, reloadUser, retryBootstrap }),
    [user, status, login, logout, reloadUser, retryBootstrap],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>')
  return ctx
}
