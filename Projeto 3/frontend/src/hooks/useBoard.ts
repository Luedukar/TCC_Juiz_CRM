import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { api } from '../lib/api'
import { readSnapshot, writeSnapshot } from '../lib/snapshot'
import type { Board } from '../lib/types'

export const boardKey = (ownerId: string | null) => ['board', ownerId ?? 'all'] as const

export function useBoard(ownerId: string | null) {
  const qc = useQueryClient()
  const snapshotKey = `board.${ownerId ?? 'all'}`
  // Cópia local do último quadro: serve de ponto de partida se a API estiver fora do ar.
  const snapshot = useMemo(() => readSnapshot<Board>(snapshotKey), [snapshotKey])

  const query = useQuery({
    queryKey: boardKey(ownerId),
    queryFn: ({ signal }) =>
      api<Board>(`/deals/board${ownerId ? `?owner_id=${ownerId}` : ''}`, { signal, timeoutMs: 15_000 }),
    initialData: snapshot?.data,
    initialDataUpdatedAt: snapshot?.savedAt,
    // Atualização periódica, pausada enquanto há movimentação em andamento.
    refetchInterval: () => (qc.isMutating() > 0 ? false : 30_000),
    refetchIntervalInBackground: false,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  })

  useEffect(() => {
    if (query.data && query.dataUpdatedAt) writeSnapshot(snapshotKey, query.data, query.dataUpdatedAt)
  }, [query.data, query.dataUpdatedAt, snapshotKey])

  return query
}
