import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Temperature, User } from '../lib/types'
import { makeBoard, makeDeal, STAGES } from '../test/factories'
import { BoardToolbar } from './BoardToolbar'

const board = makeBoard(STAGES, [
  makeDeal('a', 's1', { value: '1000' }),
  makeDeal('b', 's1', { value: '2000' }),
  makeDeal('c', 's2', { value: '4000' }),
  makeDeal('d', 's3', { value: '9999', status: 'won' }), // ganho: fora do resumo do funil
])

const seller = { id: 'u1', name: 'Ana Souza', email: 'ana@x.com', role: 'sales_rep', is_active: true, last_login_at: null, terms_accepted_at: null } as User

function props(overrides: Partial<React.ComponentProps<typeof BoardToolbar>> = {}) {
  return {
    board,
    search: '',
    onSearch: vi.fn(),
    temperatures: new Set<Temperature>(),
    onToggleTemperature: vi.fn(),
    isManager: false,
    users: [seller],
    ownerId: null,
    onOwnerChange: vi.fn(),
    onNewDeal: vi.fn(),
    onRefresh: vi.fn(),
    isFetching: false,
    disabled: false,
    ...overrides,
  }
}

describe('BoardToolbar', () => {
  it('resume apenas negócios em aberto (sem ganhos/perdidos) e a previsão ponderada', () => {
    render(<BoardToolbar {...props()} />)
    expect(screen.getByText('3 negócios')).toBeInTheDocument()
    expect(screen.getByText(/7\.000/)).toBeInTheDocument() // 1000 + 2000 + 4000
    expect(screen.getByText(/2\.300/)).toBeInTheDocument() // 3000 × 10% + 4000 × 50%
  })

  it('filtro por vendedor só existe para o gestor (RBAC na interface)', () => {
    const { rerender } = render(<BoardToolbar {...props({ isManager: false })} />)
    expect(screen.queryByLabelText('Filtrar por vendedor')).not.toBeInTheDocument()
    rerender(<BoardToolbar {...props({ isManager: true })} />)
    expect(screen.getByLabelText('Filtrar por vendedor')).toBeInTheDocument()
  })

  it('gestor escolhe um vendedor ou volta para todos', async () => {
    const p = props({ isManager: true })
    render(<BoardToolbar {...p} />)
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por vendedor'), 'u1')
    expect(p.onOwnerChange).toHaveBeenCalledWith('u1')
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por vendedor'), '')
    expect(p.onOwnerChange).toHaveBeenLastCalledWith(null)
  })

  it('filtros de temperatura refletem o estado e disparam o toggle', async () => {
    const p = props({ temperatures: new Set<Temperature>(['hot']) })
    render(<BoardToolbar {...p} />)
    expect(screen.getByRole('button', { name: 'Quente' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Frio' })).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(screen.getByRole('button', { name: 'Frio' }))
    expect(p.onToggleTemperature).toHaveBeenCalledWith('cold')
  })

  it('"Novo negócio" fica desabilitado em modo somente leitura', () => {
    render(<BoardToolbar {...props({ disabled: true })} />)
    expect(screen.getByRole('button', { name: /Novo negócio/ })).toBeDisabled()
  })

  it('busca notifica a digitação', async () => {
    const p = props()
    render(<BoardToolbar {...p} />)
    await userEvent.type(screen.getByLabelText('Buscar negócios'), 'a')
    expect(p.onSearch).toHaveBeenCalledWith('a')
  })
})
