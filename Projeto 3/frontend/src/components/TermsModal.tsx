import { useState } from 'react'
import { ApiError } from '../lib/api'
import { Modal } from './Modal'

interface Props {
  onAccept: () => Promise<void>
  onLogout: () => void
}

/** LGPD: o uso do sistema exige o aceite registrado dos termos e da política de privacidade. */
export function TermsModal({ onAccept, onLogout }: Props) {
  const [checked, setChecked] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function accept() {
    setPending(true)
    setError(null)
    try {
      await onAccept()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível registrar o aceite. Tente novamente.')
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal title="Termos de uso e privacidade">
      <p className="text-sm text-slate-600">
        Este sistema trata dados pessoais de contatos comerciais (nome, e-mail, telefone e histórico de interações) para fins de gestão de
        relacionamento, conforme a Lei Geral de Proteção de Dados (LGPD). O acesso e as alterações são registrados para auditoria.
      </p>
      <label className="mt-4 flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        <span>Li e concordo com os Termos de Uso e com a Política de Privacidade.</span>
      </label>
      {error && (
        <p role="alert" className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onLogout}>
          Sair
        </button>
        <button type="button" className="btn-primary" disabled={!checked || pending} onClick={accept}>
          {pending ? 'Registrando…' : 'Aceitar e continuar'}
        </button>
      </div>
    </Modal>
  )
}
