import { describe, expect, it } from 'vitest'
import { makeDeal } from '../test/factories'
import { COLUMN_PREFIX, resolveDrop } from './dnd'

// Coluna s1: A, B, C   |   Coluna s2: X, Y   |   Coluna s3: vazia
const A = makeDeal('A', 's1')
const B = makeDeal('B', 's1')
const C = makeDeal('C', 's1')
const X = makeDeal('X', 's2')
const Y = makeDeal('Y', 's2')

const dealsById = new Map([A, B, C, X, Y].map((d) => [d.id, d]))
const visible = new Map([
  ['s1', [A, B, C]],
  ['s2', [X, Y]],
  ['s3', []],
])

describe('resolveDrop — mesma coluna', () => {
  it('mover para baixo coloca o card depois do alvo', () => {
    // A solto sobre B: ordem final B, A, C
    expect(resolveDrop('A', 'B', dealsById, visible)).toEqual({ stageId: 's1', aboveId: 'B', belowId: 'C' })
  })

  it('mover para cima coloca o card antes do alvo', () => {
    // C solto sobre A: ordem final C, A, B
    expect(resolveDrop('C', 'A', dealsById, visible)).toEqual({ stageId: 's1', aboveId: null, belowId: 'A' })
  })

  it('soltar no lugar de origem não gera movimento', () => {
    expect(resolveDrop('B', 'B', dealsById, visible)).toBeNull()
  })

  it('soltar na área da própria coluna manda o card para o fim', () => {
    expect(resolveDrop('A', COLUMN_PREFIX + 's1', dealsById, visible)).toEqual({ stageId: 's1', aboveId: 'C', belowId: null })
  })

  it('card que já é o último, solto na área da coluna, não gera movimento', () => {
    expect(resolveDrop('C', COLUMN_PREFIX + 's1', dealsById, visible)).toBeNull()
  })
})

describe('resolveDrop — outra coluna', () => {
  it('entra antes do card sobre o qual foi solto', () => {
    expect(resolveDrop('A', 'Y', dealsById, visible)).toEqual({ stageId: 's2', aboveId: 'X', belowId: 'Y' })
  })

  it('soltar sobre o primeiro card coloca no topo', () => {
    expect(resolveDrop('A', 'X', dealsById, visible)).toEqual({ stageId: 's2', aboveId: null, belowId: 'X' })
  })

  it('soltar na área da coluna coloca no fim', () => {
    expect(resolveDrop('A', COLUMN_PREFIX + 's2', dealsById, visible)).toEqual({ stageId: 's2', aboveId: 'Y', belowId: null })
  })

  it('coluna vazia não tem vizinhos', () => {
    expect(resolveDrop('A', COLUMN_PREFIX + 's3', dealsById, visible)).toEqual({ stageId: 's3', aboveId: null, belowId: null })
  })
})

describe('resolveDrop — casos inválidos e filtros', () => {
  it('ignora card ativo desconhecido', () => {
    expect(resolveDrop('Z', 'A', dealsById, visible)).toBeNull()
  })

  it('ignora alvo desconhecido', () => {
    expect(resolveDrop('A', 'Z', dealsById, visible)).toBeNull()
  })

  it('ignora coluna desconhecida', () => {
    expect(resolveDrop('A', COLUMN_PREFIX + 'nope', dealsById, visible)).toBeNull()
  })

  it('com filtro ativo usa como vizinhos apenas os cards visíveis', () => {
    // B está oculto pelo filtro: o usuário vê A e C
    const filtered = new Map([
      ['s1', [A, C]],
      ['s2', [X, Y]],
    ])
    expect(resolveDrop('X', 'C', dealsById, filtered)).toEqual({ stageId: 's1', aboveId: 'A', belowId: 'C' })
  })
})
