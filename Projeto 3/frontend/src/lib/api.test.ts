import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, onAuthLost, tokenStore } from './api'

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

const pair = (access: string, refresh: string) => ({ access_token: access, refresh_token: refresh, token_type: 'bearer', expires_in: 900 })
const apiError = (code: string, message = 'erro', extra: Record<string, unknown> = {}) => ({ error: { code, message, request_id: 'req-1', ...extra } })

const isRefresh = (url: unknown) => String(url).endsWith('/auth/refresh')
const authHeader = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.Authorization

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  tokenStore.clear()
  onAuthLost(null)
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api — requisições', () => {
  it('envia o access token como Bearer', async () => {
    tokenStore.set(pair('a1', 'r1'))
    fetchMock.mockResolvedValue(json(200, { ok: true }))
    await api('/deals')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/deals')
    expect(authHeader(init)).toBe('Bearer a1')
  })

  it('serializa o corpo como JSON', async () => {
    fetchMock.mockResolvedValue(json(200, {}))
    await api('/deals', { method: 'POST', body: { title: 'X' }, auth: false })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"title":"X"}')
  })

  it('devolve undefined em respostas 204', async () => {
    fetchMock.mockResolvedValue(json(204, null))
    expect(await api('/deals/1', { method: 'DELETE' })).toBeUndefined()
  })
})

describe('api — renovação de sessão', () => {
  function sessionHandler(onRefresh: (init?: RequestInit) => Response | Promise<Response>) {
    return async (url: unknown, init?: RequestInit) => {
      if (isRefresh(url)) return onRefresh(init)
      return authHeader(init) === 'Bearer a2' ? json(200, { ok: true }) : json(401, apiError('token_expired'))
    }
  }

  it('renova o token ao receber 401 e repete a requisição', async () => {
    tokenStore.set(pair('a1', 'r1'))
    fetchMock.mockImplementation(sessionHandler(() => json(200, pair('a2', 'r2'))))
    expect(await api('/deals')).toEqual({ ok: true })
    expect(fetchMock.mock.calls).toHaveLength(3) // original, refresh, nova tentativa
    expect(tokenStore.getRefresh()).toBe('r2')
  })

  it('requisições simultâneas compartilham uma única renovação', async () => {
    tokenStore.set(pair('a1', 'r1'))
    fetchMock.mockImplementation(sessionHandler(() => json(200, pair('a2', 'r2'))))
    await Promise.all([api('/deals'), api('/companies'), api('/contacts')])
    expect(fetchMock.mock.calls.filter(([url]) => isRefresh(url))).toHaveLength(1)
  })

  it('refresh rejeitado encerra a sessão e avisa a aplicação', async () => {
    tokenStore.set(pair('a1', 'r1'))
    const lost = vi.fn()
    onAuthLost(lost)
    fetchMock.mockImplementation(sessionHandler(() => json(401, apiError('invalid_refresh_token'))))
    await expect(api('/deals')).rejects.toMatchObject({ status: 401 })
    expect(lost).toHaveBeenCalledTimes(1)
    expect(tokenStore.getRefresh()).toBeNull()
  })

  it('refresh com servidor inacessível mantém a sessão e reporta falha de rede', async () => {
    tokenStore.set(pair('a1', 'r1'))
    const lost = vi.fn()
    onAuthLost(lost)
    fetchMock.mockImplementation(
      sessionHandler(() => {
        throw new TypeError('Failed to fetch')
      }),
    )
    await expect(api('/deals')).rejects.toMatchObject({ kind: 'network' })
    expect(lost).not.toHaveBeenCalled()
    expect(tokenStore.getRefresh()).toBe('r1')
  })

  it('conflito de refresh (outra aba renovou) repete com o token gravado por ela', async () => {
    tokenStore.set(pair('a1', 'r1'))
    const bodies: string[] = []
    fetchMock.mockImplementation(
      sessionHandler((init) => {
        const sent = JSON.parse(String(init?.body)).refresh_token as string
        bodies.push(sent)
        if (bodies.length === 1) {
          tokenStore.set(pair('a-outra-aba', 'r3')) // a outra aba gravou o token novo
          return json(401, apiError('refresh_conflict'))
        }
        return json(200, pair('a2', 'r4'))
      }),
    )
    expect(await api('/deals')).toEqual({ ok: true })
    expect(bodies).toEqual(['r1', 'r3'])
    expect(tokenStore.getRefresh()).toBe('r4')
  })

  it('401 em rota sem autenticação (login) não tenta renovar', async () => {
    fetchMock.mockResolvedValue(json(401, apiError('invalid_credentials', 'E-mail ou senha incorretos.')))
    await expect(api('/auth/login', { method: 'POST', body: {}, auth: false })).rejects.toThrow('E-mail ou senha incorretos.')
    expect(fetchMock.mock.calls).toHaveLength(1)
  })
})

describe('api — erros amigáveis', () => {
  it('falha de rede vira ApiError de conectividade', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await api('/deals').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).kind).toBe('network')
    expect((error as ApiError).isConnectivity).toBe(true)
    expect((error as ApiError).message).toContain('conectar')
  })

  it('timeout aborta a requisição lenta', async () => {
    fetchMock.mockImplementation(
      (_url: unknown, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        }),
    )
    const error = await api('/deals', { timeoutMs: 30 }).catch((e: unknown) => e)
    expect((error as ApiError).kind).toBe('timeout')
    expect((error as ApiError).isConnectivity).toBe(true)
  })

  it('lê código, mensagem, detalhes por campo e request_id do backend', async () => {
    const details = [{ field: 'title', message: 'Informe o título.' }]
    fetchMock.mockResolvedValue(json(422, apiError('validation_error', 'Campos inválidos.', { details })))
    const error = (await api('/deals', { method: 'POST', body: {}, auth: false }).catch((e: unknown) => e)) as ApiError
    expect(error.status).toBe(422)
    expect(error.code).toBe('validation_error')
    expect(error.details).toEqual(details)
    expect(error.requestId).toBe('req-1')
    expect(error.isConnectivity).toBe(false)
  })

  it('expõe Retry-After do rate limit', async () => {
    fetchMock.mockResolvedValue(json(429, apiError('rate_limited', 'Aguarde.'), { 'Retry-After': '7' }))
    const error = (await api('/auth/login', { method: 'POST', body: {}, auth: false }).catch((e: unknown) => e)) as ApiError
    expect(error.retryAfter).toBe(7)
  })

  it('resposta 502 sem JSON usa mensagem padrão e conta como indisponibilidade', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad Gateway</html>', { status: 502 }))
    const error = (await api('/deals').catch((e: unknown) => e)) as ApiError
    expect(error.message).toContain('indisponível')
    expect(error.isConnectivity).toBe(true)
  })
})
