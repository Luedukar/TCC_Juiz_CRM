import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import BoardPage from './pages/BoardPage'
import LoginPage from './pages/LoginPage'

function RequireAuth({ children }: { children: ReactNode }) {
  const { status, retryBootstrap } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500" role="status">
        Carregando…
      </div>
    )
  }
  if (status === 'unreachable') {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <div role="alert" className="max-w-md rounded-xl bg-white p-6 text-center shadow">
          <h1 className="text-base font-semibold">Não foi possível conectar ao servidor</h1>
          <p className="mt-2 text-sm text-slate-600">Verifique sua conexão e tente novamente. Sua sessão foi mantida.</p>
          <button type="button" className="btn-primary mt-4" onClick={retryBootstrap}>
            Tentar novamente
          </button>
        </div>
      </div>
    )
  }
  if (status === 'anonymous') return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <BoardPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
