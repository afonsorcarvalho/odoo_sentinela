import { useState } from 'react'
import { useHistory, useThreshold } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { TimeSeriesChart } from '../TimeSeriesChart'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import type { Window } from '../../lib/types'

// Container adaptador: TimeSeriesChart (presentational) exige history +
// threshold + tail (ver TimeSeriesChart.tsx) -- history vem do cache do
// TanStack Query (useHistory, buscado 1x por janela), threshold do cadastro
// do sensor (useThreshold) e tail e a cauda ao vivo local (useLiveTail),
// mesma composicao usada por SensorDetailPanel/DashboardPage. O widget nao
// expoe troca de janela (sem onWindowChange no binding) -- fixa em
// defaultWindow.
export function TimeseriesWidget({
  sensorCode,
  defaultWindow = '24h',
}: {
  sensorCode: string
  defaultWindow?: Window
}) {
  const [window] = useState<Window>(defaultWindow)
  const history = useHistory(sensorCode, window)
  const threshold = useThreshold(sensorCode)
  const { tail } = useLiveTail(sensorCode)

  if (!sensorCode) return <WidgetPlaceholder texto="Configurar sensor" />

  return <TimeSeriesChart history={history.data} threshold={threshold.data ?? null} tail={tail} />
}
