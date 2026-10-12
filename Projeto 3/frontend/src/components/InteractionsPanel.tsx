import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api, ApiError } from '../lib/api'
import { INTERACTION_ICON, INTERACTION_LABEL } from '../lib/constants'
import { formatDateTime, fromLocalInput, toLocalInput } from '../lib/format'
import type { Contact, Interaction, InteractionType, Page } from '../lib/types'
import { useToast } from './Toast'

interface Props {
  dealId: string
  contacts: Contact[]
}

export function InteractionsPanel({ dealId, contacts }: Props) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const key = ['interactions', dealId]

  const list = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => api<Page<Interaction>>(`/deals/${dealId}/interactions?page_size=50`, { signal }),
  })

  const [type, setType] = useState<InteractionType>('call')
  const [subject, setSubject] = useState('')
  const [occurredAt, setOccurredAt] = useState(() => toLocalInput(new Date().toISOString()))
  const [notes, setNotes] = useState('')
  const [contactId, setContactId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      api<Interaction>(`/deals/${dealId}/interactions`, {
        method: 'POST',
        body: {
          type,
          subject: subject.trim(),
          notes: notes.trim() || null,
          occurred_at: fromLocalInput(occurredAt),
          contact_id: contactId || null,
        },
      }),
    onSuccess: () => {
      setSubject('')
      setNotes('')
      setError(null)
      toast.push('success', 'Interação registrada.')
      void qc.invalidateQueries({ queryKey: key })
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Não foi possível registrar a interação.'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/interactions/${id}`, { method: 'DELETE' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: key }),
    onError: (e) => toast.push('error', e instanceof ApiError ? e.message : 'Não foi possível excluir a interação.'),
  })

  const canSubmit = subject.trim().length >= 2 && occurredAt !== '' && !create.isPending

  return (
    <div className="space-y-5">
      <form
        className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3"
        onSubmit={(e) => {
          e.preventDefault()
          if (canSubmit) create.mutate()
        }}
      >
        <h3 className="text-sm font-semibold">Registrar interação</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="int-type">Tipo</label>
            <select id="int-type" className="field" value={type} onChange={(e) => setType(e.target.value as InteractionType)}>
              {(Object.keys(INTERACTION_LABEL) as InteractionType[]).map((t) => (
                <option key={t} value={t}>{INTERACTION_LABEL[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="int-when">Data e hora</label>
            <input id="int-when" type="datetime-local" className="field" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label" htmlFor="int-subject">Assunto</label>
          <input id="int-subject" className="field" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Ex.: Apresentação da proposta" />
        </div>
        {contacts.length > 0 && (
          <div>
            <label className="label" htmlFor="int-contact">Contato (opcional)</label>
            <select id="int-contact" className="field" value={contactId} onChange={(e) => setContactId(e.target.value)}>
              <option value="">—</option>
              {contacts.map((c) => (
                <option key={c.id} value={c.id}>{c.full_name}</option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="label" htmlFor="int-notes">Anotações</label>
          <textarea id="int-notes" className="field" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        {error && <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex justify-end">
          <button type="submit" className="btn-primary" disabled={!canSubmit}>
            {create.isPending ? 'Salvando…' : 'Registrar'}
          </button>
        </div>
      </form>

      <section aria-label="Histórico de interações">
        <h3 className="mb-2 text-sm font-semibold">Histórico</h3>
        {list.isPending && <p className="text-sm text-slate-500">Carregando histórico…</p>}
        {list.isError && (
          <p role="alert" className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Não foi possível carregar o histórico. <button type="button" className="underline" onClick={() => list.refetch()}>Tentar novamente</button>
          </p>
        )}
        {list.data && list.data.items.length === 0 && <p className="text-sm text-slate-500">Nenhuma interação registrada ainda.</p>}
        <ol className="space-y-3">
          {list.data?.items.map((i) => (
            <li key={i.id} className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">
                  <span aria-hidden="true">{INTERACTION_ICON[i.type]} </span>
                  {i.subject}
                </p>
                {(user?.role === 'sales_manager' || user?.id === i.user.id) && (
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:text-red-600"
                    onClick={() => window.confirm('Excluir esta interação?') && remove.mutate(i.id)}
                  >
                    Excluir
                  </button>
                )}
              </div>
              <p className="text-xs text-slate-500">
                {INTERACTION_LABEL[i.type]} · {formatDateTime(i.occurred_at)} · {i.user.name}
              </p>
              {i.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{i.notes}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
