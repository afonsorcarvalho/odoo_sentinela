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
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/21\.0/)).toBeInTheDocument()
  })

  it('clicar no valor do sensor ativo chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday carouselIntervalMs={3000} />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })

  it('area com 1 sensor nao mostra dots', () => {
    render(
      <AreaCard group={singleGroup} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('area com N sensores mostra 1 dot por sensor', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('avanca automaticamente entre sensores a cada 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
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
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
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

  it('foco por teclado pausa avanco automatico; blur retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.focus(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.blur(card)
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
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
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
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    const value = screen.getByText(/30\.0/)
    expect(value.style.color).toBe(statusTextColor('crit'))
  })

  it('avancar o now faz a area cruzar para warn quando um sensor cruza para offline SEM nenhum LivePoint novo (tick, nao evento)', () => {
    vi.useFakeTimers()
    const start = 1_800_000_000_000
    vi.setSystemTime(start)
    const freshLive = {
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: start, value: 21, alarm_state: 'ok' as const },
      'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: start, value: -3.6, alarm_state: 'ok' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={freshLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    // Aggregate comeca 'ok': ambos os sensores fresh e dentro do limite.
    expect(screen.getByText('OK')).toBeInTheDocument()

    // Nenhum LivePoint novo chega -- so o relogio (useNow, tick de 30s) anda.
    // useNow so reavalia `now` em multiplos do seu intervalMs (30s) a partir
    // do mount, entao para garantir que o TICK observado fique estritamente
    // acima de DEFAULT_OFFLINE_MS (15min) avancamos alem do proximo multiplo
    // de 30s depois de 15min (900000ms -> proximo tick em 930000ms), nao so
    // 15min+1ms (que ficaria "preso" no ultimo tick <= 900000 e nao mostraria
    // a transicao). 16min cobre essa margem com folga.
    act(() => {
      vi.advanceTimersByTime(16 * 60_000)
    })
    expect(screen.getByText('Perto do limite')).toBeInTheDocument()
    expect(screen.queryByText('OK')).not.toBeInTheDocument()
  })

  it('sensor offline SEM threshold (display unknown) faz a area virar warn, nao ok/unknown', () => {
    vi.useFakeTimers()
    const start = 1_800_000_000_000
    vi.setSystemTime(start)
    const oldLive = {
      // ts muito antigo -> ja nasce offline (sem depender de tick), sem
      // threshold configurado (nao esta em thresholdsByCode) -> display
      // 'unknown'. E o caso fatal que a feature existe para fechar.
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: start - 20 * 60_000, value: 21, alarm_state: 'ok' as const },
      'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: start, value: -3.6, alarm_state: 'ok' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={{}} liveByCode={oldLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.queryByText('OK')).not.toBeInTheDocument()
    expect(screen.queryByText('Sem limite')).not.toBeInTheDocument()
    expect(screen.getByText('Perto do limite')).toBeInTheDocument()
  })

  it('sensor never (nenhum LivePoint) escala para offline apos a janela de graca (2x staleMs)', () => {
    vi.useFakeTimers()
    const start = 1_800_000_000_000
    vi.setSystemTime(start)
    const partialLive = {
      // TEMP-EXP-01 sem entrada em liveByCode -> live undefined -> freshness
      // 'never' (caso "morto no page-load", o mais perigoso da doc).
      'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: start, value: -3.6, alarm_state: 'ok' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={partialLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    // No load, 'never' ainda dentro da graca -- nao escala. Contribuicao do
    // TEMP (unknown) fica abaixo da do PRESS (ok, fresh), entao a area
    // agrega para 'ok' (worst entre unknown e ok e ok) -- nao ha falso
    // warn so por existir um sensor sem dado ainda.
    expect(screen.getByText('OK')).toBeInTheDocument()

    // Janela de graca = 2*staleMs = 10min (600000ms). useNow so reavalia em
    // multiplos de 30s a partir do mount, entao (mesma armadilha do teste
    // anterior) avancar so 10min+1ms ficaria preso no ultimo tick <= 600000.
    // 11min passa do proximo tick estrito (630000) com folga.
    act(() => {
      vi.advanceTimersByTime(11 * 60_000)
    })
    expect(screen.queryByText('OK')).not.toBeInTheDocument()
    expect(screen.getByText('Perto do limite')).toBeInTheDocument()
  })

  it('sensor stale (velho, mas nao offline) NAO altera a agregacao da area', () => {
    vi.useFakeTimers()
    const start = 1_800_000_000_000
    vi.setSystemTime(start)
    const staleLive = {
      // 10min de idade: > staleMs(5min), <= offlineMs(15min) -> 'stale', que
      // nao deve escalar a agregacao (so o valor bruto 'ok'/'ok' conta).
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: start - 10 * 60_000, value: 21, alarm_state: 'ok' as const },
      'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: start, value: -3.6, alarm_state: 'ok' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={staleLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={3000} />,
    )
    expect(screen.getByText('OK')).toBeInTheDocument()
  })

  it('carouselIntervalMs vindo por prop governa o intervalo (nao mais fixo em 3000)', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} carouselIntervalMs={100} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(99)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })
})
