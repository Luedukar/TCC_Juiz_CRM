import type { Board, Deal, Stage } from '../lib/types'

export function makeStage(id: string, name: string, extra: Partial<Stage> = {}): Stage {
  return {
    id,
    pipeline_id: 'p1',
    name,
    position: 0,
    probability: 10,
    color: '#94A3B8',
    is_won: false,
    is_lost: false,
    ...extra,
  }
}

export function makeDeal(id: string, stageId: string, extra: Partial<Deal> = {}): Deal {
  return {
    id,
    pipeline_id: 'p1',
    stage_id: stageId,
    title: `Negócio ${id}`,
    value: '1000.00',
    currency: 'BRL',
    temperature: 'cold',
    status: 'open',
    position: '1024',
    expected_close_date: null,
    next_action_type: null,
    next_action_at: null,
    next_action_note: null,
    stage_entered_at: '2026-10-01T12:00:00Z',
    closed_at: null,
    lost_reason: null,
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
    company: { id: 'c1', legal_name: 'Empresa Exemplo Ltda', trade_name: 'Exemplo' },
    owner: { id: 'u1', name: 'Ana Souza' },
    primary_contact: null,
    next_action_overdue: false,
    days_in_stage: 3,
    ...extra,
  }
}

/** Monta um quadro com totais coerentes a partir das etapas e dos cards. */
export function makeBoard(stages: Stage[], deals: Deal[]): Board {
  return {
    pipeline_id: 'p1',
    pipeline_name: 'Funil Padrão',
    generated_at: '2026-10-09T12:00:00Z',
    columns: stages.map((stage) => {
      const own = deals.filter((d) => d.stage_id === stage.id)
      return {
        stage,
        total_count: own.length,
        total_value: String(own.reduce((sum, d) => sum + Number(d.value), 0)),
        deals: own,
      }
    }),
  }
}

export const STAGES = [
  makeStage('s1', 'Prospecção', { position: 0, probability: 10 }),
  makeStage('s2', 'Proposta', { position: 1, probability: 50 }),
  makeStage('s3', 'Ganho', { position: 2, probability: 100, is_won: true }),
  makeStage('s4', 'Perdido', { position: 3, probability: 0, is_lost: true }),
]
