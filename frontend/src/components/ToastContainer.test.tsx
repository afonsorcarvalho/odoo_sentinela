import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ToastContainer } from './ToastContainer'
import { liveApi } from '../lib/api'
import type { AlarmEvent, LiveAlarme } from '../lib/types'

const AREA_NAMES = { EXPURGO: 'Expurgo' }

const EVT = (id: number, status: AlarmEvent['status'] = 'aberto'): AlarmEvent => ({
  id, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
  tipo_violacao: 'abaixo_limite', status, timestamp_deteccao: 1_753_000_000_000,
  timestamp_resolucao_sensor: null, valor_lido: -1.7, limite_configurado_snapshot: -2.5,
  usuario_responsavel: null, data_resolucao: null, observacoes: null,
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('ToastContainer', () => {
  it('nao mostra toast na primeira renderizacao (baseline, nao "tudo e novo")', () => {
    render(<ToastContainer alarms={[EVT(1)]} areaNameByCode={AREA_NAMES} loaded />)
    expect(screen.queryByText(/Expurgo/)).not.toBeInTheDocument()
  })

  it('um alarme com id novo apos a primeira renderizacao dispara um toast', () => {
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} areaNameByCode={AREA_NAMES} loaded />)
    rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} areaNameByCode={AREA_NAMES} loaded />)
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()
  })

  it('toast some sozinho apos 6s', () => {
    vi.useFakeTimers()
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} areaNameByCode={AREA_NAMES} loaded />)
    act(() => rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} areaNameByCode={AREA_NAMES} loaded />))
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(6000))
    expect(screen.queryByText(/Não conformidade — Expurgo/)).not.toBeInTheDocument()
  })

  it('nao dispara toast quando a query assenta de [] pra alarmes ja existentes (loaded=false -> true)', () => {
    const { rerender } = render(<ToastContainer alarms={[]} areaNameByCode={AREA_NAMES} loaded={false} />)
    rerender(<ToastContainer alarms={[EVT(1), EVT(2)]} areaNameByCode={AREA_NAMES} loaded />)
    expect(screen.queryByText(/Expurgo/)).not.toBeInTheDocument()
  })

  it('mostra toast ao vivo imediatamente e nao duplica quando o duravel chega', () => {
    let capturedCb: ((a: LiveAlarme) => void) | null = null
    vi.spyOn(liveApi, 'subscribeAlarme').mockImplementation((cb) => {
      capturedCb = cb
      return () => {}
    })

    const { rerender } = render(<ToastContainer alarms={[]} areaNameByCode={AREA_NAMES} loaded />)

    const liveAlarme: LiveAlarme = {
      sensor_code: 'PRESS-EXP-01',
      area_code: 'EXPURGO',
      tipo_evento: 'entrada_alarme',
      tipo_violacao: 'abaixo_limite',
      valor: -3.1,
      timestamp: '2026-07-26T12:00:00Z',
    }
    act(() => capturedCb!(liveAlarme))

    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()

    const alarmeDuravel: AlarmEvent = {
      ...EVT(1),
      timestamp_deteccao: Date.parse('2026-07-26T12:00:00Z'),
    }
    rerender(
      <ToastContainer
        alarms={[alarmeDuravel]}
        areaNameByCode={AREA_NAMES}
        loaded
      />,
    )

    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('fallback: alarme duravel sem sinal ao vivo ainda toasta', () => {
    const { rerender } = render(<ToastContainer alarms={[]} areaNameByCode={AREA_NAMES} loaded />)

    rerender(<ToastContainer alarms={[EVT(1)]} areaNameByCode={AREA_NAMES} loaded />)

    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()
  })
})
