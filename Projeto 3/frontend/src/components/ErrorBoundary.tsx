import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  failed: boolean
}

/** Última linha de defesa: erro de renderização mostra uma tela amigável em vez de página em branco. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Erro de renderização', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div role="alert" className="max-w-md rounded-xl bg-white p-6 text-center shadow">
          <h1 className="text-lg font-semibold">Algo deu errado</h1>
          <p className="mt-2 text-sm text-slate-600">Ocorreu um erro inesperado ao exibir esta tela. Recarregue a página para continuar.</p>
          <button type="button" className="btn-primary mt-4" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        </div>
      </div>
    )
  }
}
