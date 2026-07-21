import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

function makeAlarm(overrides: Partial<AlarmEvent> = {}): AlarmEvent {
  return {
    id: 1, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: 1_753_000_000_000, timestamp_resolucao_sensor: null,
    valor_lido: -1.7, limite_configurado_snapshot: -2.5,
    usuario_responsavel: null, data_resolucao: null, observacoes: null,
    ...overrides,
  }
}

describe('AlarmItem', () => {
  it('mostra area (resolvida via prop), sensor, valor e limite', () => {
    render(<AlarmItem alarm={makeAlarm()} areaName="Expurgo" />)
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
    expect(screen.getByText('Valor lido -1.7 (limite -2.5)')).toBeInTheDocument()
  })

  it('alarme ainda aberto (sem timestamp_resolucao_sensor) nao mostra nenhuma linha de resolucao', () => {
    render(<AlarmItem alarm={makeAlarm()} areaName="Expurgo" />)
    expect(screen.queryByText(/Sensor normalizado/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Resolvido por/)).not.toBeInTheDocument()
  })

  it('sensor normalizado (timestamp_resolucao_sensor) mostra horario, mesmo sem responsavel humano — este e o campo que a ingestao real popula automaticamente', () => {
    const alarm = makeAlarm({ timestamp_resolucao_sensor: Date.parse('2026-07-19T14:05:00Z') })
    render(<AlarmItem alarm={alarm} areaName="Expurgo" />)
    expect(screen.getByText(/Sensor normalizado às/)).toBeInTheDocument()
    expect(screen.queryByText(/Resolvido por/)).not.toBeInTheDocument()
  })

  it('alarme resolvido com responsavel mostra quem resolveu e quando', () => {
    const alarm = makeAlarm({
      status: 'resolvido', usuario_responsavel: 'Ana Enfermeira',
      data_resolucao: Date.parse('2026-07-19T14:05:00Z'),
    })
    render(<AlarmItem alarm={alarm} areaName="Expurgo" />)
    expect(screen.getByText(/Resolvido por Ana Enfermeira em/)).toBeInTheDocument()
  })

  it('mostra observacoes quando presentes', () => {
    const alarm = makeAlarm({ observacoes: 'Janela aberta por engano.' })
    render(<AlarmItem alarm={alarm} areaName="Expurgo" />)
    expect(screen.getByText('"Janela aberta por engano."')).toBeInTheDocument()
  })

  it('sem isNew: não aplica animação de entrada', () => {
    render(<AlarmItem alarm={makeAlarm()} areaName="Expurgo" />)
    const li = screen.getByRole('listitem')
    expect(li.className).not.toMatch(/alarm-enter/)
  })

  it('isNew: aplica classe de entrada/flash', () => {
    render(<AlarmItem alarm={makeAlarm()} areaName="Expurgo" isNew />)
    const li = screen.getByRole('listitem')
    expect(li.className).toMatch(/alarm-enter/)
  })
})
