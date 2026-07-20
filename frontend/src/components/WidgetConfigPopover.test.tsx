import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WidgetConfigPopover } from './WidgetConfigPopover'
import { useThreshold } from '../lib/queries'
import type { WidgetInstance } from '../lib/layout/schema'

vi.mock('../lib/queries', () => ({
  useSensors: () => ({
    data: [
      { sensor_code: 'S1', name: 'Sensor Um', area: { area_code: 'A1', name: 'Área Um' } },
      { sensor_code: 'S2', name: 'Sensor Dois', area: { area_code: 'A2', name: 'Área Dois' } },
    ],
  }),
  // default: sem threshold herdado (sensor sem cadastro, ou ainda carregando) —
  // testes existentes continuam vendo o texto genérico de fallback.
  useThreshold: vi.fn(() => ({ data: undefined })),
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

    it('placeholder dos limites indica que vazio usa o cadastro do sensor (sem threshold herdado)', () => {
      render(<WidgetConfigPopover widget={kpiWidget} onChange={vi.fn()} onClose={vi.fn()} />)
      expect(screen.getByLabelText('Limite mín.')).toHaveAttribute('placeholder', 'cadastro do sensor')
      expect(screen.getByLabelText('Limite máx.')).toHaveAttribute('placeholder', 'cadastro do sensor')
    })

    it('placeholder dos limites reflete o threshold herdado do sensor quando vazio', () => {
      vi.mocked(useThreshold).mockReturnValueOnce({
        data: { sensor_id: 'S1', limite_min: 10, limite_max: 90, is_valor_padrao_regulatorio: false },
      } as ReturnType<typeof useThreshold>)

      render(<WidgetConfigPopover widget={kpiWidget} onChange={vi.fn()} onClose={vi.fn()} />)

      expect(screen.getByLabelText('Limite mín.')).toHaveAttribute('placeholder', '10')
      expect(screen.getByLabelText('Limite máx.')).toHaveAttribute('placeholder', '90')
    })

    it('mostra erro inline quando limiteMin > limiteMax', () => {
      const widgetInvalido: WidgetInstance = { ...kpiWidget, options: { limiteMin: 10, limiteMax: 5 } }
      render(<WidgetConfigPopover widget={widgetInvalido} onChange={vi.fn()} onClose={vi.fn()} />)
      expect(screen.getByRole('alert')).toHaveTextContent('Limite mín. deve ser ≤ limite máx.')
    })

    it('não mostra erro inline quando os limites são válidos ou só um está preenchido', () => {
      const widgetValido: WidgetInstance = { ...kpiWidget, options: { limiteMin: 1, limiteMax: 9 } }
      render(<WidgetConfigPopover widget={widgetValido} onChange={vi.fn()} onClose={vi.fn()} />)
      expect(screen.queryByRole('alert')).toBeNull()
    })

    it('editar um campo faz MERGE com options existentes, não overwrite (regressão)', async () => {
      // options multi-chave: se setOption virasse overwrite ({...patch} em vez de
      // {...widget.options, ...patch}), label e limiteMax desapareceriam do payload.
      const kpiComOptionsMultiChave: WidgetInstance = {
        ...kpiWidget,
        options: { label: 'A', limiteMax: 50 },
      }
      const onChange = vi.fn()
      render(<WidgetConfigPopover widget={kpiComOptionsMultiChave} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.type(screen.getByLabelText('Limite mín.'), '1')

      expect(onChange).toHaveBeenLastCalledWith({
        ...kpiComOptionsMultiChave,
        options: { label: 'A', limiteMax: 50, limiteMin: 1 },
      })
    })
  })

  describe('alarms — escopo', () => {
    it('trocar escopo para Área revela a seção multi-área (dropdown "Adicionar área")', async () => {
      const onChange = vi.fn()
      const { rerender } = render(<WidgetConfigPopover widget={alarmsWidget} onChange={onChange} onClose={vi.fn()} />)

      expect(screen.queryByLabelText('Adicionar área')).toBeNull()

      await userEvent.selectOptions(screen.getByLabelText('Escopo'), 'area')
      expect(onChange).toHaveBeenLastCalledWith({
        ...alarmsWidget,
        options: { ...alarmsWidget.options, scope: 'area' },
      })

      const widgetComEscopoArea: WidgetInstance = { ...alarmsWidget, options: { scope: 'area' } }
      rerender(<WidgetConfigPopover widget={widgetComEscopoArea} onChange={onChange} onClose={vi.fn()} />)
      expect(screen.getByLabelText('Adicionar área')).toBeInTheDocument()
    })

    it('voltar para Site mantém scope: site (e a seção de áreas some, sem limpar areaCodes)', async () => {
      const onChange = vi.fn()
      const widgetComEscopoArea: WidgetInstance = { ...alarmsWidget, binding: { areaCodes: ['A2'] }, options: { scope: 'area' } }
      render(<WidgetConfigPopover widget={widgetComEscopoArea} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText('Escopo'), 'site')
      expect(onChange).toHaveBeenLastCalledWith({
        ...widgetComEscopoArea,
        options: { ...widgetComEscopoArea.options, scope: 'site' },
      })
    })

    it('scope=site: seção de áreas ausente do DOM', () => {
      render(<WidgetConfigPopover widget={alarmsWidget} onChange={vi.fn()} onClose={vi.fn()} />)
      expect(screen.queryByLabelText('Adicionar área')).toBeNull()
    })
  })

  describe('alarms — multi-área (dropdown + chips)', () => {
    const alarmsAreaScope: WidgetInstance = { ...alarmsWidget, options: { scope: 'area' } }

    it('dropdown "Adicionar área" lista todas as áreas do site quando nenhuma foi escolhida ainda', () => {
      render(<WidgetConfigPopover widget={alarmsAreaScope} onChange={vi.fn()} onClose={vi.fn()} />)
      const select = screen.getByLabelText('Adicionar área')
      expect(within(select).getByRole('option', { name: 'Área Um' })).toBeInTheDocument()
      expect(within(select).getByRole('option', { name: 'Área Dois' })).toBeInTheDocument()
    })

    it('escolher uma área no dropdown adiciona chip e grava binding.areaCodes via onChange', async () => {
      const onChange = vi.fn()
      const { rerender } = render(<WidgetConfigPopover widget={alarmsAreaScope} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText('Adicionar área'), 'A2')

      expect(onChange).toHaveBeenLastCalledWith({
        ...alarmsAreaScope,
        binding: { ...alarmsAreaScope.binding, areaCodes: ['A2'] },
      })

      // Round-trip: com o pai reaplicando o widget atualizado (como o onChange real
      // faria), a chip aparece, a opção some do dropdown e o select volta ao "—".
      const widgetComA2: WidgetInstance = { ...alarmsAreaScope, binding: { areaCodes: ['A2'] } }
      rerender(<WidgetConfigPopover widget={widgetComA2} onChange={onChange} onClose={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Remover área Área Dois' })).toBeInTheDocument()
      const select = screen.getByLabelText('Adicionar área') as HTMLSelectElement
      expect(select.value).toBe('')
      expect(within(select).queryByRole('option', { name: 'Área Dois' })).toBeNull()
    })

    it('área já escolhida some das opções do dropdown "Adicionar área"', () => {
      const widgetComA2: WidgetInstance = { ...alarmsAreaScope, binding: { areaCodes: ['A2'] } }
      render(<WidgetConfigPopover widget={widgetComA2} onChange={vi.fn()} onClose={vi.fn()} />)

      const select = screen.getByLabelText('Adicionar área')
      expect(within(select).queryByRole('option', { name: 'Área Dois' })).toBeNull()
      expect(within(select).getByRole('option', { name: 'Área Um' })).toBeInTheDocument()
    })

    it('remover chip (×) tira a área de binding.areaCodes', async () => {
      const onChange = vi.fn()
      const widgetComDuasAreas: WidgetInstance = { ...alarmsAreaScope, binding: { areaCodes: ['A1', 'A2'] } }
      render(<WidgetConfigPopover widget={widgetComDuasAreas} onChange={onChange} onClose={vi.fn()} />)

      await userEvent.click(screen.getByRole('button', { name: 'Remover área Área Um' }))

      expect(onChange).toHaveBeenLastCalledWith({
        ...widgetComDuasAreas,
        binding: { ...widgetComDuasAreas.binding, areaCodes: ['A2'] },
      })
    })

    it('widget legado (binding.areaCode, sem areaCodes) mostra o chip da área legada; adicionar outra grava as duas em areaCodes', async () => {
      const onChange = vi.fn()
      const widgetLegado: WidgetInstance = { ...alarmsAreaScope, binding: { areaCode: 'A1' } }
      render(<WidgetConfigPopover widget={widgetLegado} onChange={onChange} onClose={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Remover área Área Um' })).toBeInTheDocument()

      await userEvent.selectOptions(screen.getByLabelText('Adicionar área'), 'A2')

      expect(onChange).toHaveBeenLastCalledWith({
        ...widgetLegado,
        binding: { ...widgetLegado.binding, areaCodes: ['A1', 'A2'] },
      })
    })
  })
})
