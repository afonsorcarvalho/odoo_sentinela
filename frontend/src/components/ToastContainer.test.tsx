import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ToastContainer } from './ToastContainer'
import type { AlarmEvent } from '../lib/types'

const AREA_NAMES = { EXPURGO: 'Expurgo' }

const EVT = (id: number, status: AlarmEvent['status'] = 'aberto'): AlarmEvent => ({
  id, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
  tipo_violacao: 'abaixo_limite', status, timestamp_deteccao: 1_753_000_000_000,
  timestamp_resolucao_sensor: null, valor_lido: -1.7, limite_configurado_snapshot: -2.5,
  usuario_responsavel: null, data_resolucao: null, observacoes: null,
})

afterEach(() => vi.useRealTimers())

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
})
