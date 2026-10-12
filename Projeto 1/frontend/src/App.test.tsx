import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Deal, Pipeline, Stage, User } from "./api";

const seller: User = {
  id: "seller-1",
  full_name: "Vendedora Teste",
  email: "seller@example.com",
  role: "sales_rep",
  is_active: true,
};

const pipeline: Pipeline = {
  id: "pipeline-1",
  name: "Vendas B2B",
  is_default: true,
  created_by: "manager-1",
};

const stages: Stage[] = [
  {
    id: "stage-prospecting",
    pipeline_id: pipeline.id,
    name: "Prospecção",
    position: 0,
    probability: 10,
    is_won: false,
    is_lost: false,
  },
  {
    id: "stage-qualified",
    pipeline_id: pipeline.id,
    name: "Qualificado",
    position: 1,
    probability: 35,
    is_won: false,
    is_lost: false,
  },
];

const sellerDeal: Deal = {
  id: "deal-owned",
  pipeline_id: pipeline.id,
  stage_id: stages[0].id,
  company_id: null,
  primary_contact_id: null,
  owner_id: seller.id,
  title: "Contrato da carteira",
  amount: "12500.00",
  currency: "BRL",
  temperature: "hot",
  expected_close_date: "2026-12-20",
  next_action: "Enviar proposta",
  next_action_at: "2026-10-20T14:00:00Z",
  lost_reason: null,
  created_at: "2026-10-01T12:00:00Z",
  updated_at: "2026-10-10T12:00:00Z",
  closed_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function setupApi(moveStatus = 200) {
  const calls: Array<{ url: string; method: string; body?: string }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method, body: init?.body?.toString() });

    if (url.endsWith("/auth/me")) return jsonResponse(seller);
    if (url.endsWith("/pipelines")) return jsonResponse([pipeline]);
    if (url.endsWith("/companies")) return jsonResponse([]);
    if (url.endsWith("/contacts")) return jsonResponse([]);
    if (url.endsWith(`/pipelines/${pipeline.id}/stages`)) return jsonResponse(stages);
    if (url.includes(`/deals?pipeline_id=${pipeline.id}`)) return jsonResponse([sellerDeal]);
    if (url.endsWith(`/deals/${sellerDeal.id}/stage`) && method === "POST") {
      if (moveStatus !== 200) {
        return jsonResponse({ detail: "Você não pode mover esta oportunidade." }, moveStatus);
      }
      const body = JSON.parse(String(init?.body)) as { stage_id: string };
      return jsonResponse({ ...sellerDeal, stage_id: body.stage_id });
    }
    return jsonResponse({ detail: "Rota de teste não configurada." }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

async function renderBoard() {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Pipeline de vendas" })).toBeInTheDocument();
  expect(await screen.findByRole("article", { name: "Editar oportunidade Contrato da carteira" })).toBeInTheDocument();
}

function columnFor(stageName: string): HTMLElement {
  const heading = screen.getByRole("heading", { name: stageName });
  const column = heading.closest(".kanban-column");
  if (!(column instanceof HTMLElement)) throw new Error(`Coluna "${stageName}" não encontrada.`);
  return column;
}

describe("pipeline de vendas", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("exibe apenas as oportunidades retornadas para a carteira do vendedor", async () => {
    setupApi();

    await renderBoard();

    expect(screen.getByRole("article", { name: "Editar oportunidade Contrato da carteira" })).toBeInTheDocument();
    expect(screen.queryByText("Negócio de outra carteira")).not.toBeInTheDocument();
  });

  it("move o card para a etapa escolhida e envia a movimentação à API", async () => {
    const { calls } = setupApi();
    await renderBoard();
    const card = screen.getByRole("article", { name: "Editar oportunidade Contrato da carteira" });
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn(() => sellerDeal.id),
      effectAllowed: "move",
    };

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.dragOver(columnFor("Qualificado"), { dataTransfer });
    fireEvent.drop(columnFor("Qualificado"), { dataTransfer });

    await waitFor(() => {
      expect(within(columnFor("Qualificado")).getByRole("article", {
        name: "Editar oportunidade Contrato da carteira",
      })).toBeInTheDocument();
    });
    const moveRequest = calls.find((call) => call.method === "POST" && call.url.endsWith("/deals/deal-owned/stage"));
    expect(moveRequest).toBeDefined();
    expect(JSON.parse(moveRequest?.body ?? "{}")).toEqual({ stage_id: "stage-qualified" });
    expect(await screen.findByRole("status")).toHaveTextContent("Oportunidade movida para a nova etapa.");
  });

  it("reverte a posição local e informa quando a API nega a movimentação", async () => {
    setupApi(403);
    await renderBoard();
    const card = screen.getByRole("article", { name: "Editar oportunidade Contrato da carteira" });
    const dataTransfer = {
      setData: vi.fn(),
      getData: vi.fn(() => sellerDeal.id),
      effectAllowed: "move",
    };

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(columnFor("Qualificado"), { dataTransfer });

    expect(await screen.findByRole("status")).toHaveTextContent("Você não pode mover esta oportunidade.");
    expect(within(columnFor("Prospecção")).getByRole("article", {
      name: "Editar oportunidade Contrato da carteira",
    })).toBeInTheDocument();
  });
});
