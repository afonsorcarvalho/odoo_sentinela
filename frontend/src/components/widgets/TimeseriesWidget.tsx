import { useState } from 'react'
import { useHistory, useThreshold, useSensors } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { TimeSeriesChart } from '../TimeSeriesChart'
import { WindowSelector } from '../WindowSelector'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import type { Window } from '../../lib/types'

// Container adaptador: TimeSeriesChart (presentational) exige history +
// threshold + tail (ver TimeSeriesChart.tsx) -- history vem do cache do
// TanStack Query (useHistory, buscado 1x por janela), threshold do cadastro
// do sensor (useThreshold) e tail e a cauda ao vivo local (useLiveTail),
// mesma composicao usada por SensorDetailPanel/DashboardPage. O widget agora
// expoe troca de janela via WindowSelector — mutável com useState.
export function TimeseriesWidget({
  sensorCode,
  defaultWindow = '24h',
}: {
  sensorCode: string
  defaultWindow?: Window
}) {
  const [window, setWindow] = useState<Window>(defaultWindow)
  const history = useHistory(sensorCode, window)
  const threshold = useThreshold(sensorCode)
  const { tail } = useLiveTail(sensorCode)
  const sensor = (useSensors().data ?? []).find((s) => s.sensor_code === sensorCode)

  if (!sensorCode) return <WidgetPlaceholder texto="Configurar sensor" />

  return (
    <div
      className="flex h-full flex-col rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="truncate text-sm font-bold" style={{ color: 'var(--color-ink)' }}>
          {sensor?.name ?? sensorCode}
        </span>
        <div className="ml-auto">
          <WindowSelector value={window} onChange={setWindow} />
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <TimeSeriesChart history={history.data} threshold={threshold.data ?? null} tail={tail} />
      </div>
    </div>
  )
}
