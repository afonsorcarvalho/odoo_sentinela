import { createContext } from 'react'

// Transporte da callback de drill-down (AreaCard -> SensorDetailDrawer) sem
// prop-threading pela cadeia DashboardGrid -> WidgetFrame -> registry ->
// AreaWidget (ver design doc D3, "Transporte da callback: React context").
// `null` = sem provider (modo edicao, widget isolado em teste) -> AreaWidget
// cai no no-op atual, sem regressao.
export type DrillDown = { open: (sensorCode: string) => void }

export const DrillDownContext = createContext<DrillDown | null>(null)
