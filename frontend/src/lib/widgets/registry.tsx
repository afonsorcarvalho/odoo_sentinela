import type { ReactNode } from 'react'
import type { WidgetInstance, WidgetType } from '../layout/schema'
import { AreaWidget } from '../../components/widgets/AreaWidget'
import { TimeseriesWidget } from '../../components/widgets/TimeseriesWidget'
import { AlarmsWidget } from '../../components/widgets/AlarmsWidget'
import { KpiWidget } from '../../components/widgets/KpiWidget'
import { WidgetPlaceholder } from '../../components/widgets/WidgetPlaceholder'
import type { Window } from '../types'

export type WidgetDescriptor = {
  type: WidgetType
  label: string
  needs: 'area' | 'sensor' | 'none'
  defaultSize: { w: number; h: number }
  minSize: { w: number; h: number }
  render: (widget: WidgetInstance) => ReactNode
}

export const WIDGET_REGISTRY: Record<WidgetType, WidgetDescriptor> = {
  area: {
    // minSize.h = 3: abaixo de 3 linhas (rowHeight 40 + margin 8 => h2 = 88px)
    // o chrome fixo (padding + header + divisória + nome do sensor) não deixa
    // altura para o valor, que fica clipado pelo overflow do WidgetFrame. 3
    // linhas (136px) é o mínimo em que o valor aparece com respiro.
    type: 'area', label: 'Card de área', needs: 'area',
    defaultSize: { w: 3, h: 3 }, minSize: { w: 2, h: 3 },
    render: (w) => w.binding.areaCode
      ? <AreaWidget areaCode={w.binding.areaCode} />
      : <WidgetPlaceholder texto="Configurar área" />,
  },
  timeseries: {
    type: 'timeseries', label: 'Gráfico temporal', needs: 'sensor',
    defaultSize: { w: 6, h: 4 }, minSize: { w: 3, h: 3 },
    render: (w) => w.binding.sensorCode
      ? <TimeseriesWidget sensorCode={w.binding.sensorCode} defaultWindow={w.options?.defaultWindow as Window | undefined} />
      : <WidgetPlaceholder texto="Configurar sensor" />,
  },
  alarms: {
    type: 'alarms', label: 'Painel de alarmes', needs: 'none',
    defaultSize: { w: 3, h: 6 }, minSize: { w: 2, h: 3 },
    render: (w) => <AlarmsWidget
      scope={(w.options?.scope as 'site' | 'area') ?? 'site'}
      areaCodes={w.binding.areaCodes ?? (w.binding.areaCode ? [w.binding.areaCode] : [])}
    />,
  },
  kpi: {
    type: 'kpi', label: 'KPI (valor único)', needs: 'sensor',
    defaultSize: { w: 2, h: 2 }, minSize: { w: 2, h: 2 },
    render: (w) => w.binding.sensorCode
      ? <KpiWidget
          sensorCode={w.binding.sensorCode}
          label={w.options?.label as string | undefined}
          limiteMin={w.options?.limiteMin as number | undefined}
          limiteMax={w.options?.limiteMax as number | undefined}
          casasDecimais={w.options?.casasDecimais as number | undefined}
          digitosInteiros={w.options?.digitosInteiros as number | undefined}
        />
      : <WidgetPlaceholder texto="Configurar sensor" />,
  },
}
