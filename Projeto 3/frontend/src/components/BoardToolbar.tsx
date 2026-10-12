import { TEMPERATURE, TEMPERATURES } from '../lib/constants'
import { formatMoney } from '../lib/format'
import type { Board, Temperature, User } from '../lib/types'

interface Props {
  board: Board | undefined
  search: string
  onSearch: (value: string) => void
  temperatures: Set<Temperature>
  onToggleTemperature: (t: Temperature) => void
  isManager: boolean
  users: User[]
  ownerId: string | null
  onOwnerChange: (id: string | null) => void
  onNewDeal: () => void
  onRefresh: () => void
  isFetching: boolean
  disabled: boolean
}

export function BoardToolbar(p: Props) {
  // Resumo do funil em aberto (etapas de ganho/perda ficam de fora).
  const open = p.board?.columns.filter((c) => !c.stage.is_won && !c.stage.is_lost) ?? []
  const openCount = open.reduce((sum, c) => sum + c.total_count, 0)
  const openValue = open.reduce((sum, c) => sum + Number(c.total_value), 0)
  const forecast = open.reduce((sum, c) => sum + (Number(c.total_value) * c.stage.probability) / 100, 0)

  return (
    <div className="space-y-3 border-b border-slate-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Em aberto</dt>
            <dd className="font-semibold">{openCount} negócios</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Valor no funil</dt>
            <dd className="font-semibold">{formatMoney(openValue)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Previsão ponderada</dt>
            <dd className="font-semibold">{formatMoney(forecast)}</dd>
          </div>
        </dl>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-secondary" onClick={p.onRefresh} disabled={p.isFetching} aria-label="Atualizar quadro">
            <span className={p.isFetching ? 'animate-spin' : ''} aria-hidden="true">
              ↻
            </span>
            Atualizar
          </button>
          <button type="button" className="btn-primary" onClick={p.onNewDeal} disabled={p.disabled}>
            + Novo negócio
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="w-full sm:w-64">
          <label htmlFor="deal-search" className="sr-only">
            Buscar negócios
          </label>
          <input
            id="deal-search"
            type="search"
            className="field"
            placeholder="Buscar por título ou empresa…"
            value={p.search}
            onChange={(e) => p.onSearch(e.target.value)}
          />
        </div>

        <div role="group" aria-label="Filtrar por temperatura" className="flex gap-1.5">
          {TEMPERATURES.map((t) => {
            const active = p.temperatures.has(t)
            return (
              <button
                key={t}
                type="button"
                aria-pressed={active}
                onClick={() => p.onToggleTemperature(t)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition ${
                  active ? TEMPERATURE[t].selected : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${TEMPERATURE[t].dot}`} aria-hidden="true" />
                {TEMPERATURE[t].label}
              </button>
            )
          })}
        </div>

        {p.isManager && (
          <div className="w-full sm:w-52">
            <label htmlFor="owner-filter" className="sr-only">
              Filtrar por vendedor
            </label>
            <select id="owner-filter" className="field" value={p.ownerId ?? ''} onChange={(e) => p.onOwnerChange(e.target.value || null)}>
              <option value="">Todos os vendedores</option>
              {p.users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
    </div>
  )
}
