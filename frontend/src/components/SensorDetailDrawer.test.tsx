import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ECharts mockado (sem canvas em jsdom) — SensorDetailDrawer monta
// SensorDetailPanel, que monta TimeSeriesChart. Mesmo padrao de
// SensorDetailPanel.test.tsx.
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

const SENSORS = [
  { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
]

// Mesmo padrao de mock de TimeseriesWidget.test.tsx: mocka o modulo de
// queries inteiro, useHistory como vi.fn() espionavel (assinatura chamada).
vi.mock('../lib/queries', () => ({
  useSensors: () => ({ data: SENSORS }),
  useHistory: vi.fn(() => ({ data: undefined })),
  useThreshold: () => ({ data: { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false } }),
}))
vi.mock('../lib/useLiveTail', () => ({
  useLiveTail: () => ({ last: { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' }, tail: [] }),
}))

import { SensorDetailDrawer } from './SensorDetailDrawer'

function setup(overrides: Partial<{ sensorCode: string; onSelectSensor: (c: string) => void; onClose: () => void }> = {}) {
  const onSelectSensor = overrides.onSelectSensor ?? vi.fn()
  const onClose = overrides.onClose ?? vi.fn()
  const sensorCode = overrides.sensorCode ?? 'TEMP-EXP-01'
  const utils = render(
    <SensorDetailDrawer sensorCode={sensorCode} onSelectSensor={onSelectSensor} onClose={onClose} />,
  )
  return { ...utils, onSelectSensor, onClose }
}

describe('SensorDetailDrawer', () => {
  it('renderiza o SensorDetailPanel com o sensor certo (titulo e valor)', () => {
    setup({ sensorCode: 'TEMP-EXP-01' })
    expect(screen.getByText('Expurgo · Temperatura')).toBeInTheDocument()
    expect(screen.getByText('21.0')).toBeInTheDocument()
  })

  it('trocar window no WindowSelector dispara useHistory com a nova janela', async () => {
    const { useHistory } = await import('../lib/queries')
    setup({ sensorCode: 'TEMP-EXP-01' })
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(useHistory).toHaveBeenLastCalledWith('TEMP-EXP-01', '7d')
  })

  it('botao de metrica dentro do painel chama onSelectSensor com o outro codigo, sem fechar', async () => {
    const { onSelectSensor, onClose } = setup({ sensorCode: 'TEMP-EXP-01' })
    await userEvent.click(screen.getByRole('button', { name: 'Pressão' }))
    expect(onSelectSensor).toHaveBeenCalledWith('PRESS-EXP-01')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('fechar pelo botao ✕ chama onClose', async () => {
    const { onClose } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('fechar pela tecla Esc chama onClose', () => {
    const { onClose } = setup()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('fechar clicando no backdrop chama onClose', async () => {
    const { onClose } = setup()
    await userEvent.click(screen.getByTestId('sensor-detail-drawer-backdrop'))
    expect(onClose).toHaveBeenCalled()
  })

  it('foco vai para dentro do drawer ao abrir (focus trap ativo)', async () => {
    setup()
    const dialog = screen.getByRole('dialog')
    // FloatingFocusManager move o foco num queueMicrotask (para esperar
    // setters de layout effect rodarem) -- precisa de um flush assincrono.
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
  })

  it('painel usa classe responsiva de slide (drawer-panel)', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog.className).toMatch(/drawer-panel/)
  })
})
