import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WidgetConfigPopover } from './WidgetConfigPopover'
import type { WidgetInstance } from '../lib/layout/schema'

vi.mock('../lib/queries', () => ({
  useSensors: () => ({
    data: [
      { sensor_code: 'S1', name: 'Sensor Um', area: { area_code: 'A1', name: 'Área Um' } },
      { sensor_code: 'S2', name: 'Sensor Dois', area: { area_code: 'A2', name: 'Área Dois' } },
    ],
  }),
}))

const tsWidget: WidgetInstance = {
  id: 't1', type: 'timeseries', layout: { x: 0, y: 0, w: 6, h: 4 },
  binding: { sensorCode: 'S1' }, options: { defaultWindow: '24h' },
}
const kpiWidget: WidgetInstance = {
  id: 'k1', type: 'kpi', layout: { x: 0, y: 0, w: 2, h: 2 },
  binding: { sensorCode: 'S1' }, options: {},
}
const alarmsWidget: WidgetInstance = {
  id: 'a1', type: 'alarms', layout: { x: 0, y: 0, w: 3, h: 6 },
  binding: {}, options: { scope: 'site' },
}

describe('WidgetConfigPopover — config por tipo (B2 T3)', () => {
  describe('timeseries', () => {
    it('mostra o WindowSelector e escolher janela grava options.defaultWindow', async () => {
      const onChange = vi.fn()
      render(<WidgetConfigPopover widget={tsWidget} onChange={onChange} onClose={vi.fn()} />)

      expect(screen.getByRole('group', { name: 'Janela temporal' })).toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: '7d' }))
      expect(onChange).toHaveBeenCalledWith({
        ...tsWidget,
        options: { ...tsWidget.options, defaultWindow: '7d' },
      })
    })
  })

  describe('kpi', () => {
    it('editar rótulo, limite mín. e limite máx. grava em options', async () => {
      const onChange = vi.fn()
      render(<WidgetConfigPopover widget={kpiWidget} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.type(screen.getByLabelText('Rótulo'), 'X')
      expect(onChange).toHaveBeenLastCalledWith({ ...kpiWidget, options: { ...kpiWidget.options, label: 'X' } })

      await userEvent.type(screen.getByLabelText('Limite mín.'), '1')
      expect(onChange).toHaveBeenLastCalledWith({ ...kpiWidget, options: { ...kpiWidget.options, limiteMin: 1 } })

      await userEvent.type(screen.getByLabelText('Limite máx.'), '9')
      expect(onChange).toHaveBeenLastCalledWith({ ...kpiWidget, options: { ...kpiWidget.options, limiteMax: 9 } })
    })

    it('placeholder dos limites indica que vazio usa o cadastro do sensor', () => {
      render(<WidgetConfigPopover widget={kpiWidget} onChange={vi.fn()} onClose={vi.fn()} />)
      expect(screen.getByLabelText('Limite mín.')).toHaveAttribute('placeholder', 'cadastro do sensor')
      expect(screen.getByLabelText('Limite máx.')).toHaveAttribute('placeholder', 'cadastro do sensor')
    })
  })

  describe('alarms', () => {
    it('trocar escopo para Área revela o select de área e grava binding.areaCode', async () => {
      const onChange = vi.fn()
      const { rerender } = render(<WidgetConfigPopover widget={alarmsWidget} onChange={onChange} onClose={vi.fn()} />)

      expect(screen.queryByLabelText('Área')).toBeNull()

      await userEvent.selectOptions(screen.getByLabelText('Escopo'), 'area')
      expect(onChange).toHaveBeenLastCalledWith({
        ...alarmsWidget,
        options: { ...alarmsWidget.options, scope: 'area' },
      })

      const widgetComEscopoArea: WidgetInstance = { ...alarmsWidget, options: { scope: 'area' } }
      rerender(<WidgetConfigPopover widget={widgetComEscopoArea} onChange={onChange} onClose={vi.fn()} />)
      expect(screen.getByLabelText('Área')).toBeInTheDocument()

      await userEvent.selectOptions(screen.getByLabelText('Área'), 'A2')
      expect(onChange).toHaveBeenLastCalledWith({
        ...widgetComEscopoArea,
        binding: { ...widgetComEscopoArea.binding, areaCode: 'A2' },
      })
    })

    it('voltar para Site mantém scope: site', async () => {
      const onChange = vi.fn()
      const widgetComEscopoArea: WidgetInstance = { ...alarmsWidget, binding: { areaCode: 'A2' }, options: { scope: 'area' } }
      render(<WidgetConfigPopover widget={widgetComEscopoArea} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText('Escopo'), 'site')
      expect(onChange).toHaveBeenLastCalledWith({
        ...widgetComEscopoArea,
        options: { ...widgetComEscopoArea.options, scope: 'site' },
      })
    })
  })
})
