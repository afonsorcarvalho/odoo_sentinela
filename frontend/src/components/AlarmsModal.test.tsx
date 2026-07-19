import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AlarmsModal } from './AlarmsModal'
import type { AlarmEvent } from '../lib/types'

const AREA_NAMES = { EXPURGO: 'Expurgo', PREPARO: 'Preparo' }

function makeAlarm(overrides: Partial<AlarmEvent>): AlarmEvent {
  return {
    id: 1, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: Date.parse('2026-07-18T15:19:00Z'), timestamp_resolucao_sensor: null,
    valor_lido: -1.7, limite_configurado_snapshot: -2.5,
    usuario_responsavel: null, data_resolucao: null, observacoes: null,
    ...overrides,
  }
}

const ALARMS: AlarmEvent[] = [
  makeAlarm({ id: 1, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO', timestamp_deteccao: Date.parse('2026-07-18T15:19:00Z') }),
  makeAlarm({ id: 2, sensor_code: 'TEMP-PRE-01', area_code: 'PREPARO', timestamp_deteccao: Date.parse('2026-07-17T09:00:00Z') }),
]

describe('AlarmsModal', () => {
  it('mostra todos os alarmes recebidos', () => {
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={() => {}} />)
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('filtra por texto (sensor ou area)', () => {
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('Buscar por sensor ou área'), { target: { value: 'preparo' } })
    expect(screen.queryByText('Expurgo · PRESS-EXP-01')).not.toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('filtra por data', () => {
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2026-07-17' } })
    expect(screen.queryByText('Expurgo · PRESS-EXP-01')).not.toBeInTheDocument()
    expect(screen.getByText('Preparo · TEMP-PRE-01')).toBeInTheDocument()
  })

  it('sem resultados no filtro, mostra mensagem', () => {
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('Buscar por sensor ou área'), { target: { value: 'zzz' } })
    expect(screen.getByText('Nenhum alarme encontrado.')).toBeInTheDocument()
  })

  it('chama onClose ao clicar no botao fechar', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('chama onClose ao pressionar Escape', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('chama onClose ao clicar no overlay', () => {
    const onClose = vi.fn()
    render(<AlarmsModal alarms={ALARMS} areaNameByCode={AREA_NAMES} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('alarms-modal-overlay'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('filtra por data usando fuso local, nao UTC', () => {
    // Testa que a comparacao usa Date getters (data local), nao slice(0, 10) (UTC).
    // Mocka os getters para garantir que local e UTC diferem, independente do timezone da maquina.
    const ts = Date.parse('2026-07-18T23:30:00Z')
    const alarm = makeAlarm({ id: 99, timestamp_deteccao: ts })

    const getFullYearSpy = vi.spyOn(Date.prototype, 'getFullYear').mockReturnValue(2026)
    const getMonthSpy = vi.spyOn(Date.prototype, 'getMonth').mockReturnValue(6) // 0-indexed, entao julho
    const getDateSpy = vi.spyOn(Date.prototype, 'getDate').mockReturnValue(19) // dia local = 19

    try {
      render(<AlarmsModal alarms={[alarm]} areaNameByCode={AREA_NAMES} onClose={() => {}} />)

      fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2026-07-19' } })
      expect(screen.getByText(/PRESS-EXP-01/)).toBeInTheDocument()

      fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2026-07-18' } })
      expect(screen.queryByText(/PRESS-EXP-01/)).not.toBeInTheDocument()
    } finally {
      getFullYearSpy.mockRestore()
      getMonthSpy.mockRestore()
      getDateSpy.mockRestore()
    }
  })
})
