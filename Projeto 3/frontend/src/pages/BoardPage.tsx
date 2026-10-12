import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { BoardSkeleton } from '../components/BoardSkeleton'
import { BoardToolbar } from '../components/BoardToolbar'
import { ConnectionBanner } from '../components/ConnectionBanner'
import { DealDrawer } from '../components/DealDrawer'
import { KanbanBoard, type DropRequest } from '../components/KanbanBoard'
import { LostReasonModal } from '../components/LostReasonModal'
import { TermsModal } from '../components/TermsModal'
import { useToast } from '../components/Toast'
import { boardKey, useBoard } from '../hooks/useBoard'
import { useDelayedFlag } from '../hooks/useDelayedFlag'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { api, ApiError } from '../lib/api'
import { moveDealInBoard } from '../lib/boardOps'
import type { Board, Deal, Page, Temperature, User } from '../lib/types'

interface MoveInput {
  dealId: string
  stageId: string
  aboveId: string | null
  belowId: string | null
  lostReason?: string
}

type DrawerState = { mode: 'create' } | { mode: 'edit'; dealId: string } | null

export default function BoardPage() {
  const { user, logout, reloadUser } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const online = useOnlineStatus()
  const isManager = user?.role === 'sales_manager'

  const [ownerId, setOwnerId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [temperatures, setTemperatures] = useState<Set<Temperature>>(new Set())
  const [drawer, setDrawer] = useState<DrawerState>(null)
  const [pendingLost, setPendingLost] = useState<DropRequest | null>(null)

  const effectiveOwner = isManager ? ownerId : null
  const board = useBoard(effectiveOwner)
  const users = useQuery({
    queryKey: ['users'],
    queryFn: ({ signal }) => api<Page<User>>('/users?page_size=100', { signal }),
    enabled: isManager,
  })
  const isSlow = useDelayedFlag(board.isFetching, 3000)

  // Com falha de conexão o quadro é exibido em modo leitura (dados salvos).
  const readOnly = !online || board.isError

  const filter = useCallback(
    (deal: Deal) => {
      if (temperatures.size > 0 && !temperatures.has(deal.temperature)) return false
      const term = search.trim().toLowerCase()
      if (!term) return true
      return `${deal.title} ${deal.company.legal_name} ${deal.company.trade_name ?? ''}`.toLowerCase().includes(term)
    },
    [temperatures, search],
  )
  const filtered = temperatures.size > 0 || search.trim() !== ''

  const move = useMutation({
    mutationKey: ['move'],
    mutationFn: (m: MoveInput) =>
      api<Deal>(`/deals/${m.dealId}/move`, {
        method: 'POST',
        body: { stage_id: m.stageId, above_id: m.aboveId, below_id: m.belowId, lost_reason: m.lostReason },
      }),
    // Atualização otimista: o card muda de lugar na hora; se a API recusar, volta ao estado anterior.
    onMutate: async (m) => {
      const key = boardKey(effectiveOwner)
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<Board>(key)
      if (previous) qc.setQueryData<Board>(key, moveDealInBoard(previous, m.dealId, m.stageId, m.aboveId, m.belowId))
      return { previous, key }
    },
    onError: (error, _m, ctx) => {
      if (ctx?.previous) qc.setQueryData(ctx.key, ctx.previous)
      toast.push(
        'error',
        error instanceof ApiError && error.isConnectivity
          ? 'Sem conexão com o servidor: o negócio voltou para a posição original. Tente novamente.'
          : error instanceof ApiError
            ? error.message
            : 'Não foi possível mover o negócio.',
      )
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ['board'] }), // sincroniza com o servidor
  })

  function handleDrop(request: DropRequest) {
    if (readOnly) return
    if (request.stage.is_lost && request.deal.status !== 'lost') {
      setPendingLost(request) // pede o motivo antes de mover
      return
    }
    move.mutate({ dealId: request.deal.id, stageId: request.stage.id, aboveId: request.aboveId, belowId: request.belowId })
  }

  const allDeals = useMemo(() => board.data?.columns.flatMap((c) => c.deals) ?? [], [board.data])
  const editingDeal = drawer?.mode === 'edit' ? allDeals.find((d) => d.id === drawer.dealId) : undefined
  const stages = useMemo(() => board.data?.columns.map((c) => c.stage) ?? [], [board.data])

  function toggleTemperature(t: Temperature) {
    setTemperatures((cur) => {
      const next = new Set(cur)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between gap-3 bg-slate-900 px-4 py-2.5 text-white">
        <div className="flex items-baseline gap-3">
          <span className="text-base font-semibold">CRM B2B</span>
          <span className="text-sm text-slate-300">{board.data?.pipeline_name ?? 'Funil de vendas'}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-slate-300 sm:inline">
            {user?.name} · {isManager ? 'Gestor de vendas' : 'Vendedor'}
          </span>
          <button type="button" className="rounded border border-slate-600 px-2.5 py-1 hover:bg-slate-800" onClick={() => void logout()}>
            Sair
          </button>
        </div>
      </header>

      <ConnectionBanner
        online={online}
        hasData={board.data !== undefined}
        isError={board.isError}
        isSlow={isSlow}
        isFetching={board.isFetching}
        updatedAt={board.dataUpdatedAt}
        onRetry={() => void board.refetch()}
      />

      <BoardToolbar
        board={board.data}
        search={search}
        onSearch={setSearch}
        temperatures={temperatures}
        onToggleTemperature={toggleTemperature}
        isManager={isManager}
        users={users.data?.items ?? []}
        ownerId={ownerId}
        onOwnerChange={setOwnerId}
        onNewDeal={() => setDrawer({ mode: 'create' })}
        onRefresh={() => void board.refetch()}
        isFetching={board.isFetching}
        disabled={readOnly || stages.length === 0}
      />

      <main className="min-h-0 flex-1">
        {board.data ? (
          board.data.columns.length === 0 ? (
            <p className="p-8 text-center text-sm text-slate-500">Este funil ainda não tem etapas. Peça a um gestor para configurá-las.</p>
          ) : (
            <KanbanBoard
              board={board.data}
              filter={filter}
              filtered={filtered}
              readOnly={readOnly}
              showOwner={isManager}
              onOpenDeal={(deal) => setDrawer({ mode: 'edit', dealId: deal.id })}
              onDrop={handleDrop}
            />
          )
        ) : board.isError ? (
          <div role="alert" className="mx-auto mt-16 max-w-md rounded-xl bg-white p-6 text-center shadow">
            <h2 className="text-base font-semibold">Não foi possível carregar o funil</h2>
            <p className="mt-2 text-sm text-slate-600">
              {board.error instanceof ApiError ? board.error.message : 'Ocorreu um erro inesperado.'}
            </p>
            <button type="button" className="btn-primary mt-4" onClick={() => void board.refetch()} disabled={board.isFetching}>
              {board.isFetching ? 'Tentando…' : 'Tentar novamente'}
            </button>
          </div>
        ) : (
          <BoardSkeleton />
        )}
      </main>

      {drawer && (drawer.mode === 'create' || editingDeal) && (
        <DealDrawer
          key={drawer.mode === 'edit' ? drawer.dealId : 'new'}
          mode={drawer.mode}
          deal={editingDeal}
          stages={stages}
          isManager={isManager}
          users={users.data?.items ?? []}
          onClose={() => setDrawer(null)}
          onSaved={() => {
            setDrawer(null)
            void qc.invalidateQueries({ queryKey: ['board'] })
          }}
        />
      )}

      {pendingLost && (
        <LostReasonModal
          dealTitle={pendingLost.deal.title}
          onCancel={() => setPendingLost(null)}
          onConfirm={(reason) => {
            move.mutate({
              dealId: pendingLost.deal.id,
              stageId: pendingLost.stage.id,
              aboveId: pendingLost.aboveId,
              belowId: pendingLost.belowId,
              lostReason: reason,
            })
            setPendingLost(null)
          }}
        />
      )}

      {user && !user.terms_accepted_at && (
        <TermsModal
          onAccept={async () => {
            await api<User>('/auth/accept-terms', { method: 'POST' })
            await reloadUser()
          }}
          onLogout={() => void logout()}
        />
      )}
    </div>
  )
}
