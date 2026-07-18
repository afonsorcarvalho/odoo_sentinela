import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { AlarmPanel } from './AlarmPanel'
import type { AlarmEvent } from '../lib/types'

const ABERTO: AlarmEvent = {
  id: 1, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
  tipo_violacao: 'abaixo_limite', status: 'aberto', timestamp_deteccao: '2026-07-18T15:19:00Z',
  valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
}

describe('AlarmPanel', () => {
  it('lista vazia mostra estado "Nenhum alarme ativo"', () => {
    render(<AlarmPanel alarms={[]} />)
    expect(screen.getByText('Nenhum alarme ativo.')).toBeInTheDocument()
  })

  it('com alarmes, mostra contador e o tipo em maiusculas', () => {
    render(<AlarmPanel alarms={[ABERTO]} />)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('NÃO CONFORMIDADE')).toBeInTheDocument()
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
  })
})
