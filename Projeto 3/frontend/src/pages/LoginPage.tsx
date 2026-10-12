import { useEffect, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../lib/api'

export default function LoginPage() {
  const { status, login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  // Contagem regressiva quando o backend responde 429 (rate limit) com Retry-After.
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  if (status === 'authenticated') return <Navigate to="/" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (pending || cooldown > 0) return
    setPending(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
        if (err.status === 429 && err.retryAfter) setCooldown(err.retryAfter)
      } else {
        setError('Não foi possível entrar. Tente novamente.')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow" aria-labelledby="login-title">
        <div>
          <h1 id="login-title" className="text-xl font-semibold">CRM B2B</h1>
          <p className="text-sm text-slate-500">Entre com sua conta para acessar o funil de vendas.</p>
        </div>

        {error && (
          <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
            {cooldown > 0 && <span className="block text-xs opacity-80">Nova tentativa em {cooldown}s.</span>}
          </p>
        )}

        <div>
          <label className="label" htmlFor="email">E-mail</label>
          <input id="email" type="email" autoComplete="username" required className="field" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Senha</label>
          <input id="password" type="password" autoComplete="current-password" required className="field" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        <button type="submit" className="btn-primary w-full" disabled={pending || cooldown > 0}>
          {pending ? 'Entrando…' : cooldown > 0 ? `Aguarde ${cooldown}s` : 'Entrar'}
        </button>
      </form>
    </main>
  )
}
