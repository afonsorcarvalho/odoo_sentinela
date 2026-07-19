import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
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

function makeAlarm(id: number): AlarmEvent {
  return {
    id, sensor_code: `SNR-${id}`, area: { area_code: 'EXPURGO', name: 'Expurgo' },
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: `2026-07-18T15:${String(id).padStart(2, '0')}:00Z`,
    valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
  }
}

describe('AlarmPanel — limite visivel e "Ver mais"', () => {
  it('com mais alarmes que o limite, renderiza so os N mais recentes e o botao "Ver mais"', () => {
    const alarms = Array.from({ length: 12 }, (_, i) => makeAlarm(i))
    const { container } = render(<AlarmPanel alarms={alarms} onVerMais={() => {}} />)
    const items = container.querySelectorAll('ul li')
    expect(items).toHaveLength(8)
    expect(screen.getByRole('button', { name: 'Ver mais (4)' })).toBeInTheDocument()
  })

  it('com alarmes dentro do limite, nao mostra botao "Ver mais"', () => {
    const alarms = Array.from({ length: 5 }, (_, i) => makeAlarm(i))
    render(<AlarmPanel alarms={alarms} onVerMais={() => {}} />)
    expect(screen.queryByRole('button', { name: /Ver mais/ })).not.toBeInTheDocument()
  })

  it('clicar em "Ver mais" chama onVerMais', () => {
    const alarms = Array.from({ length: 12 }, (_, i) => makeAlarm(i))
    const onVerMais = vi.fn()
    render(<AlarmPanel alarms={alarms} onVerMais={onVerMais} />)
    screen.getByRole('button', { name: 'Ver mais (4)' }).click()
    expect(onVerMais).toHaveBeenCalledTimes(1)
  })
})
