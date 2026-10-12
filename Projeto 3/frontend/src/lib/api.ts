import type { TokenPair } from './types'

const BASE_URL: string = import.meta.env.VITE_API_URL ?? '/api/v1'
const REFRESH_KEY = 'crm.refresh_token'

export type ApiErrorKind = 'network' | 'timeout' | 'http'

export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  kind: ApiErrorKind
  status: number
  code: string
  details: FieldError[]
  requestId?: string
  retryAfter?: number

  constructor(
    kind: ApiErrorKind,
    message: string,
    extra: { status?: number; code?: string; details?: FieldError[]; requestId?: string; retryAfter?: number } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = extra.status ?? 0
    this.code = extra.code ?? kind
    this.details = extra.details ?? []
    this.requestId = extra.requestId
    this.retryAfter = extra.retryAfter
  }

  /** Falha de conectividade/disponibilidade (rede, timeout, 502/503/504): vale mostrar o fallback visual. */
  get isConnectivity(): boolean {
    return this.kind !== 'http' || [502, 503, 504].includes(this.status)
  }
}

// ---- Tokens -------------------------------------------------------------
// Access token só em memória; refresh token em localStorage (sobrevive ao reload).
// Melhoria futura: cookie httpOnly para o refresh token (exige ajuste no backend).
let accessToken: string | null = null
let authLostHandler: (() => void) | null = null

export const tokenStore = {
  set(pair: TokenPair) {
    accessToken = pair.access_token
    localStorage.setItem(REFRESH_KEY, pair.refresh_token)
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  clear() {
    accessToken = null
    localStorage.removeItem(REFRESH_KEY)
  },
}

export function onAuthLost(handler: (() => void) | null) {
  authLostHandler = handler
}

// ---- Transporte ---------------------------------------------------------
async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  outerSignal?: AbortSignal,
): Promise<Response> {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const forwardAbort = () => controller.abort()
  outerSignal?.addEventListener('abort', forwardAbort)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (error) {
    if (timedOut) throw new ApiError('timeout', 'O servidor demorou para responder. Tente novamente em instantes.')
    if (outerSignal?.aborted) throw error // cancelamento intencional (ex.: troca de tela)
    throw new ApiError('network', 'Não foi possível conectar ao servidor. Verifique sua conexão.')
  } finally {
    clearTimeout(timer)
    outerSignal?.removeEventListener('abort', forwardAbort)
  }
}

const DEFAULT_HTTP_MESSAGE: Record<number, string> = {
  401: 'Sessão inválida ou expirada. Faça login novamente.',
  403: 'Você não tem permissão para realizar esta ação.',
  404: 'Recurso não encontrado.',
  429: 'Muitas tentativas. Aguarde um pouco e tente novamente.',
  502: 'Serviço temporariamente indisponível. Tente novamente em instantes.',
  503: 'Serviço temporariamente indisponível. Tente novamente em instantes.',
  504: 'O servidor demorou para responder. Tente novamente em instantes.',
}

async function parseError(res: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: FieldError[]; request_id?: string } } = {}
  try {
    body = await res.json()
  } catch {
    /* corpo vazio ou não-JSON */
  }
  const retryAfterHeader = Number(res.headers.get('Retry-After'))
  return new ApiError(
    'http',
    body.error?.message ?? DEFAULT_HTTP_MESSAGE[res.status] ?? 'Não foi possível concluir a solicitação.',
    {
      status: res.status,
      code: body.error?.code ?? 'http_error',
      details: body.error?.details ?? [],
      requestId: body.error?.request_id,
      retryAfter: Number.isFinite(retryAfterHeader) && retryAfterHeader > 0 ? retryAfterHeader : undefined,
    },
  )
}

// ---- Refresh de sessão (uma única chamada por vez) ------------------------
export type RefreshResult = 'ok' | 'rejected' | 'unreachable' | 'no_token'
let refreshing: Promise<RefreshResult> | null = null

export function refreshSession(): Promise<RefreshResult> {
  if (!refreshing) {
    refreshing = doRefresh().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

const REFRESH_CONFLICT_RETRY_MS = 300
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function doRefresh(retried = false): Promise<RefreshResult> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) return 'no_token'
  try {
    const res = await fetchWithTimeout(
      `${BASE_URL}/auth/refresh`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) },
      10_000,
    )
    if (res.ok) {
      tokenStore.set((await res.json()) as TokenPair)
      return 'ok'
    }
    if (res.status === 401 || res.status === 422) {
      const error = await parseError(res)
      if (error.code === 'refresh_conflict') {
        // Outra aba renovou a sessão quase ao mesmo tempo: espera e tenta com o token que ela gravou.
        if (!retried) {
          await sleep(REFRESH_CONFLICT_RETRY_MS)
          return doRefresh(true)
        }
        return 'unreachable' // mantém os tokens; a próxima chamada tenta de novo
      }
      tokenStore.clear() // rejeição definitiva: a sessão acabou
      return 'rejected'
    }
    return 'unreachable' // 5xx/429: mantém os tokens e tenta de novo depois
  } catch {
    return 'unreachable' // sem rede: mantém os tokens
  }
}

// ---- Chamada principal --------------------------------------------------
interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
  timeoutMs?: number
  signal?: AbortSignal
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true, timeoutMs = 10_000, signal } = options

  const run = () =>
    fetchWithTimeout(
      `${BASE_URL}${path}`,
      {
        method,
        headers: {
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(auth && accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      },
      timeoutMs,
      signal,
    )

  let res = await run()

  if (res.status === 401 && auth) {
    const result = await refreshSession()
    if (result === 'unreachable') {
      throw new ApiError('network', 'Não foi possível renovar sua sessão porque o servidor está inacessível.')
    }
    if (result === 'rejected' || result === 'no_token') {
      authLostHandler?.()
      throw await parseError(res)
    }
    res = await run()
  }

  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
