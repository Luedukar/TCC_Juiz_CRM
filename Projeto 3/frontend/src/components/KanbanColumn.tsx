import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { COLUMN_PREFIX } from '../lib/dnd'
import { formatMoney } from '../lib/format'
import type { BoardColumn, Deal } from '../lib/types'
import { SortableDealCard } from './DealCard'

interface Props {
  column: BoardColumn
  deals: Deal[] // já filtrados
  filtered: boolean
  readOnly: boolean
  showOwner: boolean
  onOpenDeal: (deal: Deal) => void
}

export function KanbanColumn({ column, deals, filtered, readOnly, showOwner, onOpenDeal }: Props) {
  const { stage } = column
  const { setNodeRef, isOver } = useDroppable({ id: COLUMN_PREFIX + stage.id, disabled: readOnly })
  const hidden = column.total_count - column.deals.length

  return (
    <section
      aria-label={`Etapa ${stage.name}`}
      className="flex max-h-full w-72 shrink-0 flex-col rounded-xl border-t-4 bg-slate-200/60"
      style={{ borderTopColor: stage.color }}
    >
      <header className="px-3 pb-2 pt-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="truncate text-sm font-semibold text-slate-800">
            {stage.is_won && <span aria-hidden="true">✅ </span>}
            {stage.is_lost && <span aria-hidden="true">❌ </span>}
            {stage.name}
          </h2>
          <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-600 shadow-sm" aria-label={`${column.total_count} negócios`}>
            {column.total_count}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          {formatMoney(column.total_value)}
          {!stage.is_won && !stage.is_lost && ` · ${stage.probability}%`}
        </p>
      </header>

      <div
        ref={setNodeRef}
        className={`flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2 transition-colors ${isOver ? 'rounded-b-xl bg-indigo-100/70' : ''}`}
      >
        <SortableContext items={deals.map((d) => d.id)} strategy={verticalListSortingStrategy}>
          {deals.map((deal) => (
            <SortableDealCard key={deal.id} deal={deal} showOwner={showOwner} onOpen={onOpenDeal} disabled={readOnly} />
          ))}
        </SortableContext>

        {deals.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-500">
            {filtered ? 'Nenhum negócio com os filtros atuais' : 'Arraste negócios para cá'}
          </p>
        )}
        {hidden > 0 && !filtered && (
          <p className="px-1 pb-1 text-center text-xs text-slate-500">Exibindo {column.deals.length} de {column.total_count} negócios</p>
        )}
      </div>
    </section>
  )
}
