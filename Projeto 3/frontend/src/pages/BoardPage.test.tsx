import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/Toast'
import { api, ApiError } from '../lib/api'
import { writeSnapshot } from '../lib/snapshot'
import type { User } from '../lib/types'
import { makeBoard, makeDeal, STAGES } from '../test/factories'
import BoardPage from './BoardPage'

const auth = vi.hoisted(() => ({ user: null as unknown }))

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return { ...actual, api: vi.fn() }
})

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: auth.user,
    status: 'authenticated',
    logout: vi.fn(),
    reloadUser: vi.fn(),
    login: vi.fn(),
    retryBootstrap: vi.fn(),
  }),
}))

const baseUser = { email: 'x@teste.com', is_active: true, last_login_at: null, terms_accepted_at: '2026-10-01T00:00:00Z' }
const manager = { ...baseUser, id: 'm1', name: 'Gestora', role: 'sales_manager' } as User
const seller = { ...baseUser, id: 'u1', name: 'Ana Souza', role: 'sales_rep' } as User

const board = makeBoard(STAGES, [makeDeal('d1', 's1', { title: 'Contrato Alfa' }), makeDeal('d2', 's2', { title: 'Projeto Beta' })])
const networkError = () => new ApiError('network', 'Não foi possível conectar ao servidor. Verifique sua conexão.')

function mockApi(boardResponse: () => Promise<unknown>) {
  vi.mocked(api).mockImplementation((async (path: string) => {
    if (path.startsWith('/deals/board')) return boardResponse()
    if (path.startsWith('/users')) return { items: [], total: 0, page: 1, page_size: 100 }
    throw new Error(`rota não mockada: ${path}`)
  }) as typeof api)
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <BoardPage />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

// useBoard tenta 2 novas vezes (1 s + 2 s) antes de declarar falha: os testes de erro esperam esse tempo.
const RETRIES_TIMEOUT = { timeout: 8000 }

beforeEach(() => {
  auth.user = manager
})

describe('BoardPage — carregamento e permissões da interface', () => {
  it('exibe as colunas e os cards do funil', async () => {
    mockApi(async () => board)
    renderPage()
    expect(await screen.findByText('Contrato Alfa')).toBeInTheDocument()
    expect(screen.getByText('Projeto Beta')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Etapa Prospecção' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Etapa Perdido' })).toBeInTheDocument()
  })

  it('gestor vê o filtro de vendedor e o cabeçalho "Gestor de vendas"', async () => {
    mockApi(async () => board)
    renderPage()
    await screen.findByText('Contrato Alfa')
    expect(screen.getByLabelText('Filtrar por vendedor')).toBeInTheDocument()
    expect(screen.getByText(/Gestor de vendas/)).toBeInTheDocument()
  })

  it('vendedor não vê o filtro de vendedor nem pede a lista de usuários', async () => {
    auth.user = seller
    mockApi(async () => board)
    renderPage()
    await screen.findByText('Contrato Alfa')
    expect(screen.queryByLabelText('Filtrar por vendedor')).not.toBeInTheDocument()
    expect(vi.mocked(api).mock.calls.some(([path]) => String(path).startsWith('/users'))).toBe(false)
  })

  it('exige aceite dos termos (LGPD) no primeiro acesso', async () => {
    auth.user = { ...seller, terms_accepted_at: null }
    mockApi(async () => board)
    renderPage()
    expect(await screen.findByRole('dialog', { name: 'Termos de uso e privacidade' })).toBeInTheDocument()
  })
})

describe('BoardPage — fallback visual', () => {
  it('mostra o esqueleto enquanto a API não responde', () => {
    mockApi(() => new Promise(() => {})) // nunca resolve
    renderPage()
    expect(screen.getByLabelText('Carregando funil de vendas')).toBeInTheDocument()
  })

  it(
    'sem dados salvos e com a API fora do ar, mostra painel de erro com nova tentativa',
    async () => {
      mockApi(async () => {
        throw networkError()
      })
      renderPage()
      expect(await screen.findByText('Não foi possível carregar o funil', {}, RETRIES_TIMEOUT)).toBeInTheDocument()
      expect(screen.getByText(/conectar ao servidor/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
    },
    15_000,
  )

  it(
    'com cópia salva e API fora do ar, mantém o quadro visível em modo somente leitura',
    async () => {
      writeSnapshot('board.all', board, Date.now() - 120_000)
      mockApi(async () => {
        throw networkError()
      })
      renderPage()

      expect(await screen.findByText('Contrato Alfa')).toBeInTheDocument() // dado salvo aparece de imediato
      expect(await screen.findByText(/última versão salva/, {}, RETRIES_TIMEOUT)).toBeInTheDocument()
      expect(screen.getByText('Contrato Alfa')).toBeInTheDocument() // continua na tela
      expect(screen.getByRole('button', { name: /Novo negócio/ })).toBeDisabled()
    },
    15_000,
  )
})
