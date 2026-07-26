import type { SensorMeta } from '../../lib/types'
import type { EntityConfig } from './types'

export type Area = SensorMeta['area'] // { area_code, name, category }

// Áreas não vêm numa lista própria — derivam dos sensores. Dedup por area_code,
// ordenado por nome (mesma resolução usada no WidgetConfigPopover).
export function deriveAreas(sensors: SensorMeta[]): Area[] {
  const byCode = new Map<string, Area>(sensors.map((s) => [s.area.area_code, s.area]))
  return Array.from(byCode.values()).sort((a, b) => a.name.localeCompare(b.name))
}

export const areaConfig: EntityConfig<Area> = {
  getId: (a) => a.area_code,
  getLabel: (a) => a.name,
  getSecondary: (a) => `${a.area_code} · ${a.category}`,
  searchText: (a) => `${a.name} ${a.area_code} ${a.category}`,
  columns: [
    { header: 'Nome', cell: (a) => a.name },
    { header: 'Código', cell: (a) => a.area_code },
    { header: 'Categoria', cell: (a) => a.category },
  ],
}

export const sensorConfig: EntityConfig<SensorMeta> = {
  getId: (s) => s.sensor_code,
  getLabel: (s) => s.name,
  getSecondary: (s) => `${s.sensor_code} · ${s.area.name} · ${s.measurement_type.name}`,
  searchText: (s) =>
    `${s.name} ${s.sensor_code} ${s.area.name} ${s.measurement_type.name} ${s.unidade} ${s.protocolo_origem}`,
  columns: [
    { header: 'Nome', cell: (s) => s.name },
    { header: 'Código', cell: (s) => s.sensor_code },
    { header: 'Área', cell: (s) => s.area.name },
    { header: 'Tipo', cell: (s) => s.measurement_type.name },
    { header: 'Unidade', cell: (s) => s.unidade },
  ],
}
