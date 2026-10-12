import {
  closestCorners,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
  type UniqueIdentifier,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { useMemo, useState } from 'react'
import { COLUMN_PREFIX, resolveDrop } from '../lib/dnd'
import type { Board, Deal, Stage } from '../lib/types'
import { DealCardView } from './DealCard'
import { KanbanColumn } from './KanbanColumn'

export interface DropRequest {
  deal: Deal
  stage: Stage
  aboveId: string | null
  belowId: string | null
}

interface Props {
  board: Board
  filter: (deal: Deal) => boolean
  filtered: boolean
  readOnly: boolean
  showOwner: boolean
  onOpenDeal: (deal: Deal) => void
  onDrop: (request: DropRequest) => void
}

export function KanbanBoard({ board, filter, filtered, readOnly, showOwner, onOpenDeal, onDrop }: Props) {
  const [activeId, setActiveId] = useState<string | null>(null)

  const sensors = useSensors(
    // distance: o clique no card não vira arraste acidental.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const stagesById = useMemo(() => new Map(board.columns.map((c) => [c.stage.id, c.stage])), [board])
  const dealsById = useMemo(() => new Map(board.columns.flatMap((c) => c.deals).map((d) => [d.id, d])), [board])
  const visibleByStage = useMemo(
    () => new Map(board.columns.map((c) => [c.stage.id, c.deals.filter(filter)])),
    [board, filter],
  )

  const activeDeal = activeId ? dealsById.get(activeId) : undefined

  function describe(id: UniqueIdentifier): string {
    const key = String(id)
    if (key.startsWith(COLUMN_PREFIX)) return `etapa ${stagesById.get(key.slice(COLUMN_PREFIX.length))?.name ?? ''}`
    const deal = dealsById.get(key)
    return deal ? `negócio ${deal.title}` : 'item'
  }

  const announcements: Announcements = {
    onDragStart: ({ active }) => `Negócio ${dealsById.get(String(active.id))?.title ?? ''} selecionado.`,
    onDragOver: ({ active, over }) =>
      over ? `Negócio ${dealsById.get(String(active.id))?.title ?? ''} sobre ${describe(over.id)}.` : undefined,
    onDragEnd: ({ active, over }) =>
      over
        ? `Negócio ${dealsById.get(String(active.id))?.title ?? ''} solto em ${describe(over.id)}.`
        : `Negócio ${dealsById.get(String(active.id))?.title ?? ''} solto fora de uma etapa.`,
    onDragCancel: ({ active }) => `Movimentação do negócio ${dealsById.get(String(active.id))?.title ?? ''} cancelada.`,
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id))
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null)
    const { active, over } = event
    if (!over) return
    const deal = dealsById.get(String(active.id))
    const target = resolveDrop(String(active.id), String(over.id), dealsById, visibleByStage)
    const stage = target ? stagesById.get(target.stageId) : undefined
    if (!deal || !target || !stage) return
    onDrop({ deal, stage, aboveId: target.aboveId, belowId: target.belowId })
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      accessibility={{
        announcements,
        screenReaderInstructions: {
          draggable:
            'Para mover o negócio, pressione espaço ou Enter. Use as setas para escolher a posição, espaço para soltar e Esc para cancelar.',
        },
      }}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <div className="flex h-full gap-3 overflow-x-auto p-4">
        {board.columns.map((column) => (
          <KanbanColumn
            key={column.stage.id}
            column={column}
            deals={visibleByStage.get(column.stage.id) ?? []}
            filtered={filtered}
            readOnly={readOnly}
            showOwner={showOwner}
            onOpenDeal={onOpenDeal}
          />
        ))}
      </div>
      <DragOverlay>{activeDeal ? <DealCardView deal={activeDeal} showOwner={showOwner} overlay /> : null}</DragOverlay>
    </DndContext>
  )
}
