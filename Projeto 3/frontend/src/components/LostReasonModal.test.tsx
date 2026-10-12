import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LostReasonModal } from './LostReasonModal'

function setup() {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(<LostReasonModal dealTitle="Contrato Alfa" onConfirm={onConfirm} onCancel={onCancel} />)
  return { onConfirm, onCancel, user: userEvent.setup() }
}

describe('LostReasonModal', () => {
  it('exige um motivo com pelo menos 3 caracteres', async () => {
    const { user } = setup()
    const confirm = screen.getByRole('button', { name: 'Marcar como perdido' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Motivo'), 'ab')
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Motivo'), 'c')
    expect(confirm).toBeEnabled()
  })

  it('não aceita apenas espaços', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('Motivo'), '     ')
    expect(screen.getByRole('button', { name: 'Marcar como perdido' })).toBeDisabled()
  })

  it('confirma com o motivo sem espaços nas pontas', async () => {
    const { user, onConfirm } = setup()
    await user.type(screen.getByLabelText('Motivo'), '  Preço alto  ')
    await user.click(screen.getByRole('button', { name: 'Marcar como perdido' }))
    expect(onConfirm).toHaveBeenCalledWith('Preço alto')
  })

  it('cancela pelo botão e pela tecla Esc', async () => {
    const { user, onCancel } = setup()
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    await user.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledTimes(2)
  })

  it('cita o negócio afetado', () => {
    setup()
    expect(screen.getByText('Contrato Alfa')).toBeInTheDocument()
  })
})
