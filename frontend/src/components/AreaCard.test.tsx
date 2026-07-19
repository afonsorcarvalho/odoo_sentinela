import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { AreaCard } from './AreaCard'
import { statusTextColor } from './statusVisuals'
import type { AreaGroup } from '../lib/aggregateStatus'

afterEach(() => vi.useRealTimers())

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}
const singleGroup: AreaGroup = {
  area: { area_code: 'SALA1', name: 'Sala 1', category: 'Sala' },
  sensors: [group.sensors[0]],
}
const thresholdsByCode = {
  'TEMP-EXP-01': { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false },
  'PRESS-EXP-01': { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true },
}
const liveByCode = {
  'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' as const },
  'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: 1, value: -3.6, alarm_state: 'ok' as const },
}

describe('AreaCard', () => {
  it('mostra nome da area e o sensor ativo (1o da lista) com valor mono', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/21\.0/)).toBeInTheDocument()
  })

  it('clicar no valor do sensor ativo chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })

  it('area com 1 sensor nao mostra dots', () => {
    render(
      <AreaCard group={singleGroup} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('area com N sensores mostra 1 dot por sensor', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('avanca automaticamente entre sensores a cada 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    expect(screen.queryByText('Temperatura')).not.toBeInTheDocument()
  })

  it('hover pausa avanco automatico; mouse leave retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.mouseEnter(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.mouseLeave(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('clicar no dot pula pro sensor certo e reinicia o ciclo de 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const dots = screen.getAllByRole('tab')
    fireEvent.click(dots[1])
    expect(screen.getByText('Pressão')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
  })

  it('cor do valor em destaque reflete alarm_state (crit)', () => {
    const critLive = {
      ...liveByCode,
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={critLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const value = screen.getByText(/30\.0/)
    expect(value.style.color).toBe(statusTextColor('crit'))
  })
})
