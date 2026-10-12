import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, ApiError } from '../lib/api'
import { NEXT_ACTION_LABEL, TEMPERATURE, TEMPERATURES } from '../lib/constants'
import { fromLocalInput, toLocalInput } from '../lib/format'
import type { Company, Contact, Deal, NextActionType, Page, Stage, Temperature, User } from '../lib/types'
import { InteractionsPanel } from './InteractionsPanel'
import { useToast } from './Toast'

interface Props {
  mode: 'create' | 'edit'
  deal?: Deal
  stages: Stage[]
  isManager: boolean
  users: User[]
  defaultStageId?: string
  onClose: () => void
  onSaved: () => void
}

interface FormState {
  title: string
  companyId: string
  contactId: string
  value: string
  temperature: Temperature
  expectedClose: string
  nextType: NextActionType | ''
  nextAt: string
  nextNote: string
  stageId: string
  ownerId: string
}

function initialForm(deal: Deal | undefined, defaultStageId: string): FormState {
  return {
    title: deal?.title ?? '',
    companyId: deal?.company.id ?? '',
    contactId: deal?.primary_contact?.id ?? '',
    value: deal ? String(Number(deal.value)) : '',
    temperature: deal?.temperature ?? 'cold',
    expectedClose: deal?.expected_close_date ?? '',
    nextType: deal?.next_action_type ?? '',
    nextAt: toLocalInput(deal?.next_action_at),
    nextNote: deal?.next_action_note ?? '',
    stageId: deal?.stage_id ?? defaultStageId,
    ownerId: deal?.owner.id ?? '',
  }
}

/** Aceita "1500", "1500.50" e "1.500,50". */
function parseValue(raw: string): string | null {
  const text = raw.trim()
  if (text === '') return '0'
  const normalized = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text
  return /^\d+(\.\d{1,2})?$/.test(normalized) ? normalized : null
}

export function DealDrawer({ mode, deal, stages, isManager, users, defaultStageId, onClose, onSaved }: Props) {
  const qc = useQueryClient()
  const toast = useToast()
  const openStages = useMemo(() => stages.filter((s) => !s.is_won && !s.is_lost), [stages])
  const [form, setForm] = useState<FormState>(() => initialForm(deal, defaultStageId ?? openStages[0]?.id ?? ''))
  const [tab, setTab] = useState<'details' | 'history'>('details')
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({})
  const [serverError, setServerError] = useState<ApiError | null>(null)
  const [newCompany, setNewCompany] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }))

  const companies = useQuery({
    queryKey: ['companies', 'options'],
    queryFn: ({ signal }) => api<Page<Company>>('/companies?page_size=100', { signal }),
  })
  const contacts = useQuery({
    queryKey: ['contacts', form.companyId],
    queryFn: ({ signal }) => api<Page<Contact>>(`/contacts?company_id=${form.companyId}&page_size=100`, { signal }),
    enabled: form.companyId !== '',
  })

  const createCompany = useMutation({
    mutationFn: (legal_name: string) => api<Company>('/companies', { method: 'POST', body: { legal_name } }),
    onSuccess: async (company) => {
      await qc.invalidateQueries({ queryKey: ['companies'] })
      setForm((f) => ({ ...f, companyId: company.id, contactId: '' }))
      setNewCompany(null)
      toast.push('success', 'Empresa criada.')
    },
    onError: (e) => toast.push('error', e instanceof ApiError ? e.message : 'Não foi possível criar a empresa.'),
  })

  const save = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      mode === 'create'
        ? api<Deal>('/deals', { method: 'POST', body: payload })
        : api<Deal>(`/deals/${deal!.id}`, { method: 'PATCH', body: payload }),
    onSuccess: () => {
      toast.push('success', mode === 'create' ? 'Negócio criado.' : 'Alterações salvas.')
      onSaved()
    },
    onError: (e) => {
      if (e instanceof ApiError) setServerError(e)
      else toast.push('error', 'Não foi possível salvar o negócio.')
    },
  })

  const remove = useMutation({
    mutationFn: () => api<void>(`/deals/${deal!.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.push('success', 'Negócio excluído.')
      onSaved()
    },
    onError: (e) => toast.push('error', e instanceof ApiError ? e.message : 'Não foi possível excluir o negócio.'),
  })

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {}
    if (form.title.trim().length < 2) errors.title = 'Informe o título do negócio.'
    if (!form.companyId) errors.company_id = 'Selecione a empresa.'
    if (parseValue(form.value) === null) errors.value = 'Valor inválido. Use números, ex.: 1500 ou 1.500,50.'
    if (form.nextAt && !form.nextType) errors.next_action_type = 'Escolha o tipo da próxima ação.'
    if (form.nextType && !form.nextAt) errors.next_action_at = 'Informe data e hora da próxima ação.'
    return errors
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    setServerError(null)
    const errors = validate()
    setClientErrors(errors)
    if (Object.keys(errors).length > 0) return

    const payload: Record<string, unknown> = {
      title: form.title.trim(),
      company_id: form.companyId,
      primary_contact_id: form.contactId || null,
      value: parseValue(form.value),
      temperature: form.temperature,
      expected_close_date: form.expectedClose || null,
      next_action_type: form.nextType || null,
      next_action_at: fromLocalInput(form.nextAt),
      next_action_note: form.nextNote.trim() || null,
    }
    if (mode === 'create') {
      payload.stage_id = form.stageId || undefined
      if (isManager && form.ownerId) payload.owner_id = form.ownerId
    } else if (isManager && form.ownerId && form.ownerId !== deal!.owner.id) {
      payload.owner_id = form.ownerId
    }
    save.mutate(payload)
  }

  const fieldError = (name: string) => clientErrors[name] ?? serverError?.details.find((d) => d.field === name)?.message
  const stageName = stages.find((s) => s.id === deal?.stage_id)?.name
  const Err = ({ name }: { name: string }) => {
    const msg = fieldError(name)
    return msg ? <p className="mt-1 text-xs text-red-600">{msg}</p> : null
  }

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden="true" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-lg flex-col bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 id="drawer-title" className="text-base font-semibold">
              {mode === 'create' ? 'Novo negócio' : deal?.title}
            </h2>
            {mode === 'edit' && stageName && <p className="text-xs text-slate-500">Etapa: {stageName} · arraste o card para mover</p>}
          </div>
          <button type="button" className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>

        {mode === 'edit' && (
          <div role="tablist" className="flex gap-1 border-b border-slate-200 px-5">
            {(['details', 'history'] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                  tab === t ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {t === 'details' ? 'Detalhes' : 'Interações'}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === 'history' && deal ? (
            <InteractionsPanel dealId={deal.id} contacts={contacts.data?.items ?? []} />
          ) : (
            <form id="deal-form" onSubmit={submit} className="space-y-4" noValidate>
              {serverError && (
                <div role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
                  {serverError.message}
                  {serverError.requestId && <span className="mt-0.5 block text-xs opacity-70">Código de suporte: {serverError.requestId}</span>}
                </div>
              )}

              <div>
                <label className="label" htmlFor="f-title">Título *</label>
                <input id="f-title" className="field" maxLength={200} value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Ex.: Licenças anuais — Empresa X" />
                <Err name="title" />
              </div>

              <div>
                <label className="label" htmlFor="f-company">Empresa *</label>
                {newCompany === null ? (
                  <div className="flex gap-2">
                    <select
                      id="f-company"
                      className="field"
                      value={form.companyId}
                      onChange={(e) => setForm((f) => ({ ...f, companyId: e.target.value, contactId: '' }))}
                    >
                      <option value="">{companies.isPending ? 'Carregando…' : 'Selecione…'}</option>
                      {companies.data?.items.map((c) => (
                        <option key={c.id} value={c.id}>{c.trade_name ?? c.legal_name}</option>
                      ))}
                      {deal && !companies.data?.items.some((c) => c.id === deal.company.id) && (
                        <option value={deal.company.id}>{deal.company.trade_name ?? deal.company.legal_name}</option>
                      )}
                    </select>
                    <button type="button" className="btn-secondary shrink-0" onClick={() => setNewCompany('')}>+ Nova</button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <input
                      id="f-company"
                      className="field"
                      autoFocus
                      placeholder="Razão social da nova empresa"
                      value={newCompany}
                      onChange={(e) => setNewCompany(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn-primary shrink-0"
                      disabled={newCompany.trim().length < 2 || createCompany.isPending}
                      onClick={() => createCompany.mutate(newCompany.trim())}
                    >
                      Criar
                    </button>
                    <button type="button" className="btn-secondary shrink-0" onClick={() => setNewCompany(null)}>Cancelar</button>
                  </div>
                )}
                {companies.isError && <p className="mt-1 text-xs text-amber-700">Não foi possível carregar as empresas. Tente reabrir o formulário.</p>}
                <Err name="company_id" />
              </div>

              <div>
                <label className="label" htmlFor="f-contact">Contato principal</label>
                <select id="f-contact" className="field" value={form.contactId} onChange={(e) => set('contactId', e.target.value)} disabled={!form.companyId}>
                  <option value="">—</option>
                  {contacts.data?.items.map((c) => (
                    <option key={c.id} value={c.id}>{c.full_name}</option>
                  ))}
                </select>
                <Err name="primary_contact_id" />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="f-value">Valor (R$)</label>
                  <input id="f-value" inputMode="decimal" className="field" value={form.value} onChange={(e) => set('value', e.target.value)} placeholder="0,00" />
                  <Err name="value" />
                </div>
                <div>
                  <label className="label" htmlFor="f-close">Previsão de fechamento</label>
                  <input id="f-close" type="date" className="field" value={form.expectedClose} onChange={(e) => set('expectedClose', e.target.value)} />
                </div>
              </div>

              <fieldset>
                <legend className="label">Temperatura do lead</legend>
                <div className="flex gap-2">
                  {TEMPERATURES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={form.temperature === t}
                      onClick={() => set('temperature', t)}
                      className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition ${
                        form.temperature === t ? TEMPERATURE[t].selected : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${TEMPERATURE[t].dot}`} aria-hidden="true" />
                      {TEMPERATURE[t].label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <fieldset className="space-y-3 rounded-lg border border-slate-200 p-3">
                <legend className="px-1 text-xs font-medium text-slate-600">Próxima ação</legend>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label" htmlFor="f-next-type">Tipo</label>
                    <select id="f-next-type" className="field" value={form.nextType} onChange={(e) => set('nextType', e.target.value as NextActionType | '')}>
                      <option value="">Nenhuma</option>
                      {(Object.keys(NEXT_ACTION_LABEL) as NextActionType[]).map((t) => (
                        <option key={t} value={t}>{NEXT_ACTION_LABEL[t]}</option>
                      ))}
                    </select>
                    <Err name="next_action_type" />
                  </div>
                  <div>
                    <label className="label" htmlFor="f-next-at">Data e hora</label>
                    <input id="f-next-at" type="datetime-local" className="field" value={form.nextAt} onChange={(e) => set('nextAt', e.target.value)} />
                    <Err name="next_action_at" />
                  </div>
                </div>
                <div>
                  <label className="label" htmlFor="f-next-note">Observação</label>
                  <input id="f-next-note" className="field" maxLength={255} value={form.nextNote} onChange={(e) => set('nextNote', e.target.value)} placeholder="Ex.: Enviar proposta revisada" />
                </div>
              </fieldset>

              {mode === 'create' && (
                <div>
                  <label className="label" htmlFor="f-stage">Etapa inicial</label>
                  <select id="f-stage" className="field" value={form.stageId} onChange={(e) => set('stageId', e.target.value)}>
                    {openStages.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {isManager && (
                <div>
                  <label className="label" htmlFor="f-owner">Vendedor responsável</label>
                  <select id="f-owner" className="field" value={form.ownerId} onChange={(e) => set('ownerId', e.target.value)}>
                    {mode === 'create' && <option value="">Responsável pela empresa</option>}
                    {users.filter((u) => u.is_active).map((u) => (
                      <option key={u.id} value={u.id}>{u.name}</option>
                    ))}
                  </select>
                </div>
              )}
            </form>
          )}
        </div>

        {tab === 'details' && (
          <footer className="flex items-center justify-between gap-2 border-t border-slate-200 px-5 py-3">
            <div>
              {mode === 'edit' && (
                <button
                  type="button"
                  className="text-sm text-red-600 hover:underline disabled:opacity-50"
                  disabled={remove.isPending}
                  onClick={() => window.confirm('Excluir este negócio? Esta ação não pode ser desfeita pela interface.') && remove.mutate()}
                >
                  Excluir
                </button>
              )}
            </div>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
              <button type="submit" form="deal-form" className="btn-primary" disabled={save.isPending}>
                {save.isPending ? 'Salvando…' : mode === 'create' ? 'Criar negócio' : 'Salvar'}
              </button>
            </div>
          </footer>
        )}
      </aside>
    </div>
  )
}
