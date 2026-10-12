import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeDeal } from '../test/factories'
import { DealCardView } from './DealCard'

const hoursFromNow = (h: number) => new Date(Date.now() + h * 3_600_000).toISOString()

describe('DealCardView', () => {
  it('mostra título, empresa, valor e dias na etapa', () => {
    render(<DealCardView deal={makeDeal('d1', 's1', { title: 'Licenças anuais', value: '1500.00' })} showOwner={false} />)
    expect(screen.getByText('Licenças anuais')).toBeInTheDocument()
    expect(screen.getByText('Exemplo')).toBeInTheDocument() // nome fantasia tem prioridade
    expect(screen.getByText(/1\.500/)).toBeInTheDocument()
    expect(screen.getByText('3 d na etapa')).toBeInTheDocument()
  })

  it.each([
    ['cold', 'Frio', 'border-l-sky-500'],
    ['warm', 'Morno', 'border-l-amber-500'],
    ['hot', 'Quente', 'border-l-red-500'],
  ] as const)('temperatura %s usa rótulo e cor próprios', (temperature, label, borderClass) => {
    const { container } = render(<DealCardView deal={makeDeal('d1', 's1', { temperature })} showOwner={false} />)
    expect(screen.getByText(label)).toBeInTheDocument()
    expect(container.querySelector('article')).toHaveClass(borderClass)
  })

  describe('indicador de próxima ação', () => {
    it('alerta quando não há próxima ação definida', () => {
      render(<DealCardView deal={makeDeal('d1', 's1')} showOwner={false} />)
      expect(screen.getByText('Sem próxima ação definida')).toBeInTheDocument()
    })

    it('destaca ações atrasadas', () => {
      const deal = makeDeal('d1', 's1', { next_action_type: 'call', next_action_at: hoursFromNow(-5), next_action_overdue: true })
      render(<DealCardView deal={deal} showOwner={false} />)
      expect(screen.getByText(/Ligação atrasada/)).toBeInTheDocument()
    })

    it('mostra ação futura sem marcar atraso', () => {
      const deal = makeDeal('d1', 's1', { next_action_type: 'meeting', next_action_at: hoursFromNow(48) })
      render(<DealCardView deal={deal} showOwner={false} />)
      expect(screen.getByText(/Reunião/)).toBeInTheDocument()
      expect(screen.queryByText(/atrasada/)).not.toBeInTheDocument()
    })

    it('negócios fechados não exibem indicador', () => {
      render(<DealCardView deal={makeDeal('d1', 's3', { status: 'won' })} showOwner={false} />)
      expect(screen.queryByText('Sem próxima ação definida')).not.toBeInTheDocument()
    })
  })

  it('exibe as iniciais do responsável somente quando solicitado (visão do gestor)', () => {
    const { rerender } = render(<DealCardView deal={makeDeal('d1', 's1')} showOwner />)
    expect(screen.getByTitle('Ana Souza')).toHaveTextContent('AS')
    rerender(<DealCardView deal={makeDeal('d1', 's1')} showOwner={false} />)
    expect(screen.queryByTitle('Ana Souza')).not.toBeInTheDocument()
  })

  it('botão de edição abre o negócio', async () => {
    const onOpen = vi.fn()
    const deal = makeDeal('d1', 's1', { title: 'Contrato' })
    render(<DealCardView deal={deal} showOwner={false} onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button', { name: 'Abrir negócio Contrato' }))
    expect(onOpen).toHaveBeenCalledWith(deal)
  })

  it('sem onOpen (cartão fantasma do arraste) não renderiza botão', () => {
    render(<DealCardView deal={makeDeal('d1', 's1')} showOwner={false} overlay />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
