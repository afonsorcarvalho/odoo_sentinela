import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LiveReadout } from './LiveReadout'
import type { Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('LiveReadout', () => {
  it('mostra valor e unidade', () => {
    render(<LiveReadout value={20.5} unidade="C" threshold={t} />)
    expect(screen.getByText(/20[.,]5/)).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
  })
  it('status por rotulo textual, nao so cor (ok)', () => {
    render(<LiveReadout value={20} unidade="C" threshold={t} />)
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
  })
  it('crit quando fora da faixa', () => {
    render(<LiveReadout value={25} unidade="C" threshold={t} />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
  })
  it('estado do feed tem prioridade sobre o derivado', () => {
    render(<LiveReadout value={20} unidade="C" threshold={t} state="crit" />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
  })
  it('sem valor mostra placeholder', () => {
    render(<LiveReadout value={null} unidade="C" threshold={t} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
