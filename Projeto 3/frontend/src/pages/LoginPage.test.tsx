import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import LoginPage from './LoginPage'

const auth = vi.hoisted(() => ({ status: 'anonymous', login: vi.fn() }))

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ status: auth.status, login: auth.login, user: null }),
}))

function setup() {
  render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  )
  return userEvent.setup()
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('E-mail'), '  ana@empresa.com ')
  await user.type(screen.getByLabelText('Senha'), 'Senha-forte-123')
  await user.click(screen.getByRole('button', { name: 'Entrar' }))
}

beforeEach(() => {
  auth.status = 'anonymous'
  auth.login = vi.fn()
})

describe('LoginPage', () => {
  it('envia e-mail (sem espaços nas pontas) e senha', async () => {
    auth.login.mockResolvedValue(undefined)
    await fillAndSubmit(setup())
    expect(auth.login).toHaveBeenCalledWith('ana@empresa.com', 'Senha-forte-123')
  })

  it('mostra a mensagem do servidor quando as credenciais são inválidas', async () => {
    auth.login.mockRejectedValue(new ApiError('http', 'E-mail ou senha incorretos.', { status: 401, code: 'invalid_credentials' }))
    await fillAndSubmit(setup())
    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
  })

  it('no limite de tentativas (429) mostra a contagem regressiva e bloqueia o botão', async () => {
    auth.login.mockRejectedValue(new ApiError('http', 'Muitas tentativas em pouco tempo.', { status: 429, code: 'rate_limited', retryAfter: 30 }))
    await fillAndSubmit(setup())
    expect(await screen.findByText('Nova tentativa em 30s.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aguarde 30s' })).toBeDisabled()
  })

  it('falha inesperada mostra mensagem genérica amigável', async () => {
    auth.login.mockRejectedValue(new Error('boom'))
    await fillAndSubmit(setup())
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível entrar. Tente novamente.')
  })

  it('campos têm rótulos acessíveis e o e-mail é obrigatório', () => {
    setup()
    expect(screen.getByLabelText('E-mail')).toBeRequired()
    expect(screen.getByLabelText('Senha')).toHaveAttribute('type', 'password')
  })
})
