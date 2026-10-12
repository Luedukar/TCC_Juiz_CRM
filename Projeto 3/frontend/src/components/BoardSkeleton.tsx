/** Esqueleto do Kanban exibido enquanto o quadro carrega (ou se a API demora a responder). */
export function BoardSkeleton() {
  return (
    <div className="flex gap-3 overflow-hidden p-4" aria-busy="true" aria-label="Carregando funil de vendas">
      {Array.from({ length: 5 }).map((_, col) => (
        <div key={col} className="w-72 shrink-0 rounded-xl bg-slate-200/60 p-2">
          <div className="mb-3 h-5 w-32 animate-pulse rounded bg-slate-300" />
          <div className="space-y-2">
            {Array.from({ length: 3 - (col % 2) }).map((_, card) => (
              <div key={card} className="h-24 animate-pulse rounded-lg border border-slate-200 bg-white/80" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
