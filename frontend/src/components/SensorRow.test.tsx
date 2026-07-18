import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SensorRow } from './SensorRow'
import type { LivePoint, SensorMeta, Threshold } from '../lib/types'

function wrap(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>
}

const sensor: SensorMeta = {
  sensor_code: 'PRESS-EXP-01',
  name: 'Pressão diferencial — Expurgo',
  unidade: 'Pa',
  protocolo_origem: 'rs485',
  measurement_type: { code: 'pressao_diferencial', name: 'Pressão diferencial' },
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Descontaminação' },
}
const t: Threshold = { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true }

describe('SensorRow', () => {
  it('mostra tipo de medicao, valor+unidade, e e um link pro sensor', () => {
    const live: LivePoint = { sensor_code: 'PRESS-EXP-01', ts: 1, value: -5.2, alarm_state: 'ok' }
    render(wrap(<SensorRow sensor={sensor} threshold={t} live={live} />))
    expect(screen.getByText('Pressão diferencial')).toBeInTheDocument()
    expect(screen.getByText('-5.2')).toBeInTheDocument()
    expect(screen.getByText('Pa')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/sensor/PRESS-EXP-01')
  })

  it('status sempre com icone (nao so cor) + texto', () => {
    const live: LivePoint = { sensor_code: 'PRESS-EXP-01', ts: 1, value: -5.2, alarm_state: 'ok' }
    const { container } = render(wrap(<SensorRow sensor={sensor} threshold={t} live={live} />))
    expect(screen.getByText('Dentro da faixa')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('sem dado ao vivo ainda: mostra placeholder no valor', () => {
    render(wrap(<SensorRow sensor={sensor} threshold={t} live={undefined} />))
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
