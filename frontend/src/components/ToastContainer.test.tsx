import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ToastContainer } from './ToastContainer'
import type { AlarmEvent } from '../lib/types'

const EVT = (id: number, status: AlarmEvent['status'] = 'aberto'): AlarmEvent => ({
  id, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
  tipo_violacao: 'abaixo_limite', status, timestamp_deteccao: '2026-07-18T15:19:00Z',
  valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
})

afterEach(() => vi.useRealTimers())

describe('ToastContainer', () => {
  it('nao mostra toast na primeira renderizacao (baseline, nao "tudo e novo")', () => {
    render(<ToastContainer alarms={[EVT(1)]} />)
    expect(screen.queryByText(/Expurgo/)).not.toBeInTheDocument()
  })

  it('um alarme com id novo apos a primeira renderizacao dispara um toast', () => {
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} />)
    rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} />)
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()
  })

  it('toast some sozinho apos 6s', () => {
    vi.useFakeTimers()
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} />)
    act(() => rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} />))
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(6000))
    expect(screen.queryByText(/Não conformidade — Expurgo/)).not.toBeInTheDocument()
  })
})
