import type { Board, Deal } from './types'

/**
 * Aplica um movimento de card ao quadro em memória (atualização otimista).
 * `aboveId`/`belowId` são os vizinhos do ponto de soltura, como no backend.
 */
export function moveDealInBoard(
  board: Board,
  dealId: string,
  stageId: string,
  aboveId: string | null,
  belowId: string | null,
): Board {
  let moved: Deal | undefined
  let fromStageId = ''
  for (const column of board.columns) {
    const found = column.deals.find((d) => d.id === dealId)
    if (found) {
      moved = found
      fromStageId = column.stage.id
      break
    }
  }
  if (!moved || !board.columns.some((c) => c.stage.id === stageId)) return board

  const value = Number(moved.value)
  const columns = board.columns.map((column) => {
    const deals = column.deals.filter((d) => d.id !== dealId)
    let total_count = column.total_count
    let total_value = Number(column.total_value)

    if (fromStageId !== stageId && column.stage.id === fromStageId) {
      total_count -= 1
      total_value -= value
    }
    if (column.stage.id === stageId) {
      let index = belowId ? deals.findIndex((d) => d.id === belowId) : -1
      if (index < 0 && aboveId) {
        const above = deals.findIndex((d) => d.id === aboveId)
        index = above >= 0 ? above + 1 : -1
      }
      if (index < 0) index = deals.length

      const stageChanged = fromStageId !== stageId
      const updated: Deal = {
        ...moved!,
        stage_id: stageId,
        status: column.stage.is_won ? 'won' : column.stage.is_lost ? 'lost' : 'open',
        stage_entered_at: stageChanged ? new Date().toISOString() : moved!.stage_entered_at,
        days_in_stage: stageChanged ? 0 : moved!.days_in_stage,
      }
      deals.splice(index, 0, updated)
      if (stageChanged) {
        total_count += 1
        total_value += value
      }
    }
    return { ...column, deals, total_count, total_value: String(total_value) }
  })

  return { ...board, columns }
}
