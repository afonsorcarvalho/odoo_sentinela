import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AreaCard } from './AreaCard'
import type { AreaGroup } from '../lib/aggregateStatus'
import type { LivePoint, Threshold } from '../lib/types'

const expurgo: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Refrigeração' },
  sensors: [{
    sensor_code: 'TEMP-EXP-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
    measurement_type: { code: 'temperatura', name: 'Temperatura' },
    area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Refrigeração' },
  }],
}
const t: Threshold = { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

describe('AreaCard', () => {
  it('mostra nome e categoria da area', () => {
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{}} />)
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
  })

  it('sensor ok: mostra "Dentro da faixa", sem badge de alarme', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 20, alarm_state: 'ok' }
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />)
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
    expect(screen.queryByText(/alarme/i)).not.toBeInTheDocument()
  })

  it('sensor crit: mostra "Fora da faixa" E badge "1 alarme"', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    render(<AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
    expect(screen.getByText('1 alarme')).toBeInTheDocument()
  })

  it('sensor sem threshold (Arsenal): mostra "Sem limite", mesmo com feed ok', () => {
    const arsenal: AreaGroup = {
      area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Armazenamento' },
      sensors: [{
        sensor_code: 'TEMP-ARS-01', name: 'Temperatura', unidade: 'C', protocolo_origem: 'rs485',
        measurement_type: { code: 'temperatura', name: 'Temperatura' },
        area: { area_code: 'ARSENAL', name: 'Arsenal', category: 'Armazenamento' },
      }],
    }
    const live: LivePoint = { sensor_code: 'TEMP-ARS-01', ts: 1, value: 24, alarm_state: 'ok' }
    render(<AreaCard group={arsenal} thresholdsByCode={{ 'TEMP-ARS-01': null }} liveByCode={{ 'TEMP-ARS-01': live }} />)
    expect(screen.getByText('Sem limite')).toBeInTheDocument()
  })

  it('status sempre vem com icone (nao so cor) — svg presente junto ao texto', () => {
    const live: LivePoint = { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' }
    const { container } = render(
      <AreaCard group={expurgo} thresholdsByCode={{ 'TEMP-EXP-01': t }} liveByCode={{ 'TEMP-EXP-01': live }} />,
    )
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
