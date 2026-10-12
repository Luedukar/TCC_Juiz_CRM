export interface User {
  id: string;
  full_name: string;
  email: string;
  role: "sales_manager" | "sales_rep";
  is_active: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Pipeline {
  id: string;
  name: string;
  is_default: boolean;
  created_by: string;
}

export interface Stage {
  id: string;
  pipeline_id: string;
  name: string;
  position: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface Deal {
  id: string;
  pipeline_id: string;
  stage_id: string;
  company_id: string | null;
  primary_contact_id: string | null;
  owner_id: string;
  title: string;
  amount: string;
  currency: string;
  temperature: "cold" | "warm" | "hot";
  expected_close_date: string | null;
  next_action: string | null;
  next_action_at: string | null;
  lost_reason: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface Company {
  id: string;
  name: string;
}

export interface Contact {
  id: string;
  company_id: string | null;
  first_name: string;
  last_name: string;
  email: string | null;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
const ACCESS_KEY = "orbit.access_token";
const REFRESH_KEY = "orbit.refresh_token";

let accessToken = sessionStorage.getItem(ACCESS_KEY);
let refreshToken = sessionStorage.getItem(REFRESH_KEY);
let refreshInFlight: Promise<string | null> | null = null;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function saveTokens(tokens: TokenPair): void {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshToken) return null;
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const tokens = (await response.json()) as TokenPair;
        saveTokens(tokens);
        return tokens.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Não foi possível conectar à API. Verifique sua conexão e tente novamente.", 0);
  }

  if (response.status === 401 && !retried && refreshToken && !path.startsWith("/auth/")) {
    const token = await refreshAccessToken();
    if (token) return request<T>(path, init, true);
    clearTokens();
    window.dispatchEvent(new Event("crm:session-expired"));
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    const message =
      response.status === 429
        ? "Muitas tentativas em pouco tempo. Aguarde um instante."
        : body?.detail || `Não foi possível concluir a solicitação (${response.status}).`;
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  request,
  login: (email: string, password: string) =>
    request<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  logout: async () => {
    const currentRefreshToken = refreshToken;
    clearTokens();
    if (currentRefreshToken) {
      try {
        await request<void>("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: currentRefreshToken }),
        });
      } catch {
        // A sessão local já foi removida; a revogação também expira no servidor.
      }
    }
  },
  pipelines: () => request<Pipeline[]>("/pipelines"),
  stages: (pipelineId: string) =>
    request<Stage[]>(`/pipelines/${encodeURIComponent(pipelineId)}/stages`),
  deals: (pipelineId: string) =>
    request<Deal[]>(`/deals?pipeline_id=${encodeURIComponent(pipelineId)}`),
  companies: () => request<Company[]>("/companies"),
  contacts: () => request<Contact[]>("/contacts"),
  moveDeal: (dealId: string, stageId: string) =>
    request<Deal>(`/deals/${encodeURIComponent(dealId)}/stage`, {
      method: "POST",
      body: JSON.stringify({ stage_id: stageId }),
    }),
  updateDeal: (dealId: string, values: Record<string, unknown>) =>
    request<Deal>(`/deals/${encodeURIComponent(dealId)}`, {
      method: "PATCH",
      body: JSON.stringify(values),
    }),
  createDeal: (values: Record<string, unknown>) =>
    request<Deal>("/deals", { method: "POST", body: JSON.stringify(values) }),
};
