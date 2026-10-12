import { describe, expect, it } from 'vitest'
import { makeBoard, makeDeal, STAGES } from '../test/factories'
import { moveDealInBoard } from './boardOps'

const deals = [
  makeDeal('A', 's1', { value: '1000.00' }),
  makeDeal('B', 's1', { value: '2000.00' }),
  makeDeal('C', 's1', { value: '500.00' }),
  makeDeal('X', 's2', { value: '4000.00' }),
]
const board = makeBoard(STAGES, deals)

const ids = (b: typeof board, stageId: string) => b.columns.find((c) => c.stage.id === stageId)!.deals.map((d) => d.id)
const column = (b: typeof board, stageId: string) => b.columns.find((c) => c.stage.id === stageId)!

describe('moveDealInBoard — mesma coluna', () => {
  it('reposiciona entre dois vizinhos', () => {
    const next = moveDealInBoard(board, 'C', 's1', 'A', 'B')
    expect(ids(next, 's1')).toEqual(['A', 'C', 'B'])
  })

  it('vai para o topo quando só há vizinho abaixo', () => {
    expect(ids(moveDealInBoard(board, 'C', 's1', null, 'A'), 's1')).toEqual(['C', 'A', 'B'])
  })

  it('vai para o fim quando só há vizinho acima', () => {
    expect(ids(moveDealInBoard(board, 'A', 's1', 'C', null), 's1')).toEqual(['B', 'C', 'A'])
  })

  it('não altera contagem nem valor da coluna', () => {
    const next = moveDealInBoard(board, 'C', 's1', 'A', 'B')
    expect(column(next, 's1').total_count).toBe(3)
    expect(column(next, 's1').total_value).toBe('3500')
  })

  it('não muda a data de entrada na etapa', () => {
    const next = moveDealInBoard(board, 'C', 's1', 'A', 'B')
    expect(column(next, 's1').deals.find((d) => d.id === 'C')!.stage_entered_at).toBe('2026-10-01T12:00:00Z')
  })
})

describe('moveDealInBoard — entre colunas', () => {
  it('move o card e atualiza contagem e valor das duas colunas', () => {
    const next = moveDealInBoard(board, 'B', 's2', null, 'X')
    expect(ids(next, 's1')).toEqual(['A', 'C'])
    expect(ids(next, 's2')).toEqual(['B', 'X'])
    expect(column(next, 's1').total_count).toBe(2)
    expect(column(next, 's1').total_value).toBe('1500')
    expect(column(next, 's2').total_count).toBe(2)
    expect(column(next, 's2').total_value).toBe('6000')
  })

  it('atualiza stage_id, reinicia dias na etapa e marca a data de entrada', () => {
    const moved = column(moveDealInBoard(board, 'B', 's2', 'X', null), 's2').deals.find((d) => d.id === 'B')!
    expect(moved.stage_id).toBe('s2')
    expect(moved.days_in_stage).toBe(0)
    expect(moved.stage_entered_at === '2026-10-01T12:00:00Z').toBe(false)
  })

  it('etapa de ganho marca status won', () => {
    const moved = column(moveDealInBoard(board, 'A', 's3', null, null), 's3').deals[0]
    expect(moved.status).toBe('won')
  })

  it('etapa de perda marca status lost', () => {
    expect(column(moveDealInBoard(board, 'A', 's4', null, null), 's4').deals[0].status).toBe('lost')
  })

  it('reabrir um card fechado volta o status para open', () => {
    const closed = moveDealInBoard(board, 'A', 's3', null, null)
    expect(column(moveDealInBoard(closed, 'A', 's1', null, null), 's1').deals.find((d) => d.id === 'A')!.status).toBe('open')
  })

  it('usa o vizinho de cima quando o de baixo não existe mais', () => {
    expect(ids(moveDealInBoard(board, 'A', 's2', 'X', 'inexistente'), 's2')).toEqual(['X', 'A'])
  })
})

describe('moveDealInBoard — segurança do estado', () => {
  it('não muta o quadro original', () => {
    const snapshot = JSON.stringify(board)
    moveDealInBoard(board, 'B', 's2', null, 'X')
    expect(JSON.stringify(board)).toBe(snapshot)
  })

  it('devolve o mesmo quadro quando o card não existe', () => {
    expect(moveDealInBoard(board, 'zzz', 's2', null, null) === board).toBe(true)
  })

  it('devolve o mesmo quadro quando a etapa de destino não existe', () => {
    expect(moveDealInBoard(board, 'A', 'zzz', null, null) === board).toBe(true)
  })
})
