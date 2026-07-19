import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AlarmsModal } from './AlarmsModal'
import type { AlarmEvent } from '../lib/types'

function makeAlarm(overrides: Partial<AlarmEvent>): AlarmEvent {
  return {
    id: 1, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: '2026-07-18T15:19:00Z',
    valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
    ...overrides,
  }
}

const ALARMS: AlarmEvent[] = [
  makeAlarm({ id: 1, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' }, timestamp_deteccao: '2026-07-18T15:19:00Z' }),
  makeAlarm({ id: 2, sensor_code: 'TEMP-PRE-01', area: { area_code: 'PREPARO', name: 'Preparo' }, timestamp_deteccao: '2026-07-17T09:00:00Z' }),
]

describe('AlarmsModal', () => {
  it('mostra todos os alarmes recebidos', () => {
    render(<AlarmsModal alarms={ALARMS} onClose={() => {}} />)
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('filtra por texto (sensor ou area)', () => {
    render(<AlarmsModal alarms={ALARMS} onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('Buscar por sensor ou área'), { target: { value: 'preparo' } })
    expect(screen.queryByText('Expurgo · PRESS-EXP-01')).not.toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('filtra por data', () => {
    render(<AlarmsModal alarms={ALARMS} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2026-07-17' } })
    expect(screen.queryByText('Expurgo · PRESS-EXP-01')).not.toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('sem resultados no filtro, mostra mensagem', () => {
    render(<AlarmsModal alarms={ALARMS} onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('Buscar por sensor ou área'), { target: { value: 'zzz' } })
    expect(screen.getByText('Nenhum alarme encontrado.')).toBeInTheDocument()
  })

  it('chama onClose ao clicar no botao fechar', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('chama onClose ao pressionar Escape', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('chama onClose ao clicar no overlay', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('alarms-modal-overlay'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('filtra por data usando fuso local, nao UTC', () => {
    // Cria um alarme com timestamp perto da meia-noite UTC
    // para testar que a comparacao usa data local e nao UTC slicing
    const lateNightUTC = '2026-07-18T23:30:00Z'
    const alarm = makeAlarm({ id: 99, timestamp_deteccao: lateNightUTC })

    // Calcula a data local do alarme usando o mesmo metodo do componente
    const d = new Date(lateNightUTC)
    const pad = (n: number) => String(n).padStart(2, '0')
    const localDate = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    const utcSlicedDate = lateNightUTC.slice(0, 10) // '2026-07-18'

    render(<AlarmsModal alarms={[alarm]} onClose={() => {}} />)

    // Filtro pela data local deve incluir o alarme
    fireEvent.change(screen.getByLabelText('Data'), { target: { value: localDate } })
    expect(screen.getByText(/PRESS-EXP-01/)).toBeInTheDocument()

    // Se local e UTC diferem, filtra por UTC nao deve incluir
    if (localDate !== utcSlicedDate) {
      fireEvent.change(screen.getByLabelText('Data'), { target: { value: utcSlicedDate } })
      expect(screen.queryByText(/PRESS-EXP-01/)).not.toBeInTheDocument()
    }
  })
})
