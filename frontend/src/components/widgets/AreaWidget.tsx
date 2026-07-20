import { useContext } from 'react'
import { useSensors, useThresholds, useConfig } from '../../lib/queries'
import { useLiveStatuses } from '../../lib/useLiveStatuses'
import { groupSensorsByArea } from '../../lib/aggregateStatus'
import { AreaCard } from '../AreaCard'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import { DrillDownContext } from '../../lib/drilldown/DrillDownContext'

// Container adaptador: resolve areaCode -> AreaGroup (mesmo agrupamento
// usado pela DashboardPage) e monta os props que o AreaCard (presentational,
// sem hooks) precisa. Selecao de sensor ("alarme hoje" continua fora de
// escopo) liga ao drill-down via DrillDownContext (D3): SE houver provider
// (ramo de view da DashboardPage), clicar no valor abre o SensorDetailDrawer;
// SEM provider (modo edicao, widget isolado em teste), cai no no-op --
// comportamento inalterado, sem regressao.
export function AreaWidget({ areaCode }: { areaCode: string }) {
  const drill = useContext(DrillDownContext)
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const config = useConfig()
  const group = groupSensorsByArea(sensors).find((g) => g.area.area_code === areaCode)

  if (!group) return <WidgetPlaceholder texto={`Área "${areaCode}" indisponível`} />

  return (
    <AreaCard
      group={group}
      thresholdsByCode={thresholdsByCode}
      liveByCode={liveByCode}
      selectedSensorCode={null}
      onSelectSensor={drill ? drill.open : () => {}}
      hadAlarmToday={false}
      carouselIntervalMs={config.data?.carousel_interval_ms ?? 3000}
    />
  )
}
