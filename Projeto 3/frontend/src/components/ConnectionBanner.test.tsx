import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConnectionBanner } from './ConnectionBanner'

const base = { online: true, hasData: true, isError: false, isSlow: false, isFetching: false, updatedAt: Date.now() - 120_000, onRetry: () => {} }

describe('ConnectionBanner', () => {
  it('não mostra nada quando tudo está normal', () => {
    const { container } = render(<ConnectionBanner {...base} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('avisa quando o navegador está offline', () => {
    render(<ConnectionBanner {...base} online={false} />)
    expect(screen.getByRole('alert')).toHaveTextContent('sem conexão com a internet')
  })

  it('informa API lenta apenas enquanto a requisição está em andamento', () => {
    const { rerender } = render(<ConnectionBanner {...base} isSlow isFetching />)
    expect(screen.getByRole('status')).toHaveTextContent('demorando mais que o normal')
    rerender(<ConnectionBanner {...base} isSlow isFetching={false} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('com erro e dados salvos, explica o que está sendo exibido e permite tentar de novo', async () => {
    const onRetry = vi.fn()
    render(<ConnectionBanner {...base} isError onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/última versão salva/)
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('desabilita o botão enquanto tenta reconectar', () => {
    render(<ConnectionBanner {...base} isError isFetching />)
    expect(screen.getByRole('button', { name: 'Tentando…' })).toBeDisabled()
  })

  it('sem dados salvos o banner de erro não aparece (a tela principal mostra o painel de erro)', () => {
    const { container } = render(<ConnectionBanner {...base} hasData={false} isError />)
    expect(container).toBeEmptyDOMElement()
  })
})
