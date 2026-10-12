import { describe, expect, it } from 'vitest'
import { formatMoney, fromLocalInput, initials, relativeTime, toLocalInput } from './format'

describe('formatMoney', () => {
  it('formata em reais', () => {
    const text = formatMoney('1500.00')
    expect(text).toContain('R$')
    expect(text).toContain('1.500')
  })

  it('aceita número', () => {
    expect(formatMoney(2500)).toContain('2.500')
  })
})

describe('relativeTime', () => {
  const now = new Date('2026-10-09T12:00:00Z').getTime()

  it('descreve o passado em horas', () => {
    expect(relativeTime('2026-10-09T10:00:00Z', now)).toContain('2')
    expect(relativeTime('2026-10-09T10:00:00Z', now)).toContain('hora')
  })

  it('descreve o futuro próximo em dias', () => {
    expect(relativeTime('2026-10-10T12:00:00Z', now)).toBe('amanhã')
  })

  it('usa minutos para intervalos curtos', () => {
    expect(relativeTime('2026-10-09T11:30:00Z', now)).toContain('minuto')
  })
})

describe('datetime-local', () => {
  it('vazio vira null', () => {
    expect(fromLocalInput('')).toBeNull()
    expect(toLocalInput(null)).toBe('')
    expect(toLocalInput(undefined)).toBe('')
  })

  it('ida e volta preserva o horário local', () => {
    expect(toLocalInput(fromLocalInput('2026-10-09T14:30'))).toBe('2026-10-09T14:30')
  })

  it('gera ISO com fuso (Z), exigido pelo backend', () => {
    expect(fromLocalInput('2026-10-09T14:30')!.endsWith('Z')).toBe(true)
  })
})

describe('initials', () => {
  it('usa as duas primeiras iniciais', () => {
    expect(initials('Ana Beatriz Souza')).toBe('AB')
    expect(initials('maria')).toBe('M')
    expect(initials('')).toBe('')
  })
})
