import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { NEXT_ACTION_ICON, NEXT_ACTION_LABEL, TEMPERATURE } from '../lib/constants'
import { formatDateTime, formatMoney, initials, relativeTime } from '../lib/format'
import type { Deal } from '../lib/types'

interface ViewProps {
  deal: Deal
  showOwner: boolean
  onOpen?: (deal: Deal) => void
  overlay?: boolean
}

function NextActionIndicator({ deal }: { deal: Deal }) {
  if (deal.status !== 'open') return null

  if (!deal.next_action_at || !deal.next_action_type) {
    return (
      <p className="mt-2 rounded border border-dashed border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800">
        Sem próxima ação definida
      </p>
    )
  }

  const label = NEXT_ACTION_LABEL[deal.next_action_type]
  const when = relativeTime(deal.next_action_at)
  const tooltip = `${label} em ${formatDateTime(deal.next_action_at)}${deal.next_action_note ? ` — ${deal.next_action_note}` : ''}`

  return deal.next_action_overdue ? (
    <p title={tooltip} className="mt-2 truncate rounded bg-red-50 px-2 py-1 text-xs font-medium text-red-700">
      ⚠ {label} atrasada · {when}
    </p>
  ) : (
    <p title={tooltip} className="mt-2 truncate rounded bg-slate-50 px-2 py-1 text-xs text-slate-700">
      {NEXT_ACTION_ICON[deal.next_action_type]} {label} · {when}
    </p>
  )
}

export function DealCardView({ deal, showOwner, onOpen, overlay = false }: ViewProps) {
  const temp = TEMPERATURE[deal.temperature]
  return (
    <article
      className={`rounded-lg border border-l-4 border-slate-200 ${temp.border} bg-white p-3 text-left shadow-sm ${
        overlay ? 'rotate-2 shadow-xl ring-2 ring-indigo-300' : 'hover:shadow-md'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-2 text-sm font-semibold text-slate-900">{deal.title}</h3>
        {onOpen && (
          <button
            type="button"
            aria-label={`Abrir negócio ${deal.title}`}
            className="-mr-1 -mt-1 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            // Evita iniciar o arraste ao clicar no botão.
            onPointerDown={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              onOpen(deal)
            }}
          >
            ✏️
          </button>
        )}
      </div>

      <p className="mt-0.5 truncate text-xs text-slate-500">{deal.company.trade_name ?? deal.company.legal_name}</p>

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-900">{formatMoney(deal.value, deal.currency)}</span>
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${temp.chip}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${temp.dot}`} aria-hidden="true" />
          {temp.label}
        </span>
      </div>

      <NextActionIndicator deal={deal} />

      <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
        <span>{deal.days_in_stage === 0 ? 'Hoje na etapa' : `${deal.days_in_stage} d na etapa`}</span>
        {showOwner && (
          <span title={deal.owner.name} className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700">
            {initials(deal.owner.name)}
          </span>
        )}
      </div>
    </article>
  )
}

interface SortableProps extends ViewProps {
  disabled: boolean
}

export function SortableDealCard({ deal, showOwner, onOpen, disabled }: SortableProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: deal.id, disabled })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`${disabled ? 'cursor-default' : 'cursor-grab active:cursor-grabbing'} touch-manipulation ${isDragging ? 'opacity-40' : ''}`}
      {...attributes}
      {...listeners}
    >
      <DealCardView deal={deal} showOwner={showOwner} onOpen={onOpen} />
    </div>
  )
}
