import type { InteractionType, NextActionType, Temperature } from './types'

// Classes completas (não montadas dinamicamente) para o Tailwind detectá-las.
export const TEMPERATURE: Record<
  Temperature,
  { label: string; border: string; chip: string; dot: string; selected: string }
> = {
  cold: {
    label: 'Frio',
    border: 'border-l-sky-500',
    chip: 'bg-sky-50 text-sky-700 ring-sky-200',
    dot: 'bg-sky-500',
    selected: 'border-sky-500 bg-sky-50 text-sky-700',
  },
  warm: {
    label: 'Morno',
    border: 'border-l-amber-500',
    chip: 'bg-amber-50 text-amber-700 ring-amber-200',
    dot: 'bg-amber-500',
    selected: 'border-amber-500 bg-amber-50 text-amber-700',
  },
  hot: {
    label: 'Quente',
    border: 'border-l-red-500',
    chip: 'bg-red-50 text-red-700 ring-red-200',
    dot: 'bg-red-500',
    selected: 'border-red-500 bg-red-50 text-red-700',
  },
}

export const TEMPERATURES: Temperature[] = ['cold', 'warm', 'hot']

export const NEXT_ACTION_LABEL: Record<NextActionType, string> = {
  meeting: 'Reunião',
  email: 'E-mail',
  call: 'Ligação',
  proposal: 'Proposta',
  follow_up: 'Follow-up',
  other: 'Outra',
}

export const NEXT_ACTION_ICON: Record<NextActionType, string> = {
  meeting: '👥',
  email: '✉️',
  call: '📞',
  proposal: '📄',
  follow_up: '🔁',
  other: '📌',
}

export const INTERACTION_LABEL: Record<InteractionType, string> = {
  meeting: 'Reunião',
  email: 'E-mail',
  call: 'Ligação',
}

export const INTERACTION_ICON: Record<InteractionType, string> = {
  meeting: '👥',
  email: '✉️',
  call: '📞',
}
