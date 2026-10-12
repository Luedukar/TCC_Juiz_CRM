import { relativeTime } from '../lib/format'

interface Props {
  online: boolean
  hasData: boolean
  isError: boolean
  isSlow: boolean
  isFetching: boolean
  updatedAt: number
  onRetry: () => void
}

/** Feedback visual para falhas de rede, API lenta e exibição de dados salvos. */
export function ConnectionBanner({ online, hasData, isError, isSlow, isFetching, updatedAt, onRetry }: Props) {
  if (!online) {
    return (
      <div role="alert" className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
        Você está sem conexão com a internet. Movimentações e edições ficam desativadas até a conexão voltar.
      </div>
    )
  }

  if (isError && hasData) {
    return (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <span>
          Não foi possível atualizar o quadro. Você está vendo a última versão salva ({relativeTime(new Date(updatedAt).toISOString())}).
          Movimentações ficam desativadas até a conexão com o servidor voltar.
        </span>
        <button type="button" className="btn-secondary !py-1" onClick={onRetry} disabled={isFetching}>
          {isFetching ? 'Tentando…' : 'Tentar novamente'}
        </button>
      </div>
    )
  }

  if (isSlow && isFetching) {
    return (
      <div role="status" className="border-b border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900">
        O servidor está demorando mais que o normal. Continuamos tentando…
      </div>
    )
  }

  return null
}
