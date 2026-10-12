import type { Deal } from './types'

export const COLUMN_PREFIX = 'col:'

export interface DropTarget {
  stageId: string
  aboveId: string | null
  belowId: string | null
}

/**
 * Converte "soltei o card X sobre Y" na posição pedida ao backend (vizinhos acima/abaixo).
 * Trabalha sobre as listas VISÍVEIS (já filtradas), que são o que o usuário está vendo.
 * Retorna null quando o movimento não muda nada ou o alvo é inválido.
 */
export function resolveDrop(
  activeId: string,
  overId: string,
  dealsById: Map<string, Deal>,
  visibleByStage: Map<string, Deal[]>,
): DropTarget | null {
  const active = dealsById.get(activeId)
  if (!active) return null

  let stageId: string
  let overIndex: number | null = null

  if (overId.startsWith(COLUMN_PREFIX)) {
    stageId = overId.slice(COLUMN_PREFIX.length) // soltou na área da coluna: vai para o fim
  } else {
    const over = dealsById.get(overId)
    if (!over) return null
    stageId = over.stage_id
    overIndex = (visibleByStage.get(stageId) ?? []).findIndex((d) => d.id === overId)
    if (overIndex < 0) overIndex = null
  }

  const visible = visibleByStage.get(stageId)
  if (!visible) return null

  const originalIndex = visible.findIndex((d) => d.id === active.id)
  const withoutActive = visible.filter((d) => d.id !== active.id)
  // Mesma coluna: o índice do alvo já considera o card ativo (mesma semântica de arrayMove).
  // Outra coluna: o card entra antes do alvo.
  const index = overIndex === null ? withoutActive.length : Math.min(Math.max(overIndex, 0), withoutActive.length)

  if (active.stage_id === stageId && index === originalIndex) return null // nada mudou

  return {
    stageId,
    aboveId: withoutActive[index - 1]?.id ?? null,
    belowId: withoutActive[index]?.id ?? null,
  }
}
