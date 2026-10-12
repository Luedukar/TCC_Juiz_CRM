import { useState } from 'react'
import { Modal } from './Modal'

interface Props {
  dealTitle: string
  onConfirm: (reason: string) => void
  onCancel: () => void
}

export function LostReasonModal({ dealTitle, onConfirm, onCancel }: Props) {
  const [reason, setReason] = useState('')
  const valid = reason.trim().length >= 3

  return (
    <Modal title="Motivo da perda" onClose={onCancel}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) onConfirm(reason.trim())
        }}
      >
        <p className="text-sm text-slate-600">
          Por que o negócio <strong>{dealTitle}</strong> foi perdido? Essa informação ajuda a melhorar o funil.
        </p>
        <label className="label mt-3" htmlFor="lost-reason">
          Motivo
        </label>
        <textarea
          id="lost-reason"
          className="field"
          rows={3}
          maxLength={255}
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Ex.: Optou por concorrente com menor preço"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancelar
          </button>
          <button type="submit" className="btn-danger" disabled={!valid}>
            Marcar como perdido
          </button>
        </div>
      </form>
    </Modal>
  )
}
