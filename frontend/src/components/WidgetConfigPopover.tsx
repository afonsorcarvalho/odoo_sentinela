import { useSensors } from '../lib/queries'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import type { WidgetInstance } from '../lib/layout/schema'

export function WidgetConfigPopover({ widget, onChange, onClose }: {
  widget: WidgetInstance
  onChange: (w: WidgetInstance) => void
  onClose: () => void
}) {
  const sensors = useSensors().data ?? []
  const needs = WIDGET_REGISTRY[widget.type].needs
  const areas = Array.from(new Map(sensors.map((s) => [s.area.area_code, s.area])).values())

  return (
    <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-muted)' }}>
      <div className="mb-2 text-xs font-bold">{WIDGET_REGISTRY[widget.type].label}</div>
      {needs === 'area' && (
        <label className="block text-xs">Área
          <select
            className="mt-1 block w-full rounded border px-2 py-1 text-xs"
            style={{ borderColor: 'var(--color-muted)' }}
            value={widget.binding.areaCode ?? ''}
            onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, areaCode: e.target.value } })}
          >
            <option value="">—</option>
            {areas.map((a) => <option key={a.area_code} value={a.area_code}>{a.name}</option>)}
          </select>
        </label>
      )}
      {needs === 'sensor' && (
        <label className="block text-xs">Sensor
          <select
            className="mt-1 block w-full rounded border px-2 py-1 text-xs"
            style={{ borderColor: 'var(--color-muted)' }}
            value={widget.binding.sensorCode ?? ''}
            onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, sensorCode: e.target.value } })}
          >
            <option value="">—</option>
            {sensors.map((s) => <option key={s.sensor_code} value={s.sensor_code}>{s.name}</option>)}
          </select>
        </label>
      )}
      {needs === 'none' && (
        <div className="text-xs" style={{ color: 'var(--color-muted)' }}>Sem configuração de binding.</div>
      )}
      <button type="button" onClick={onClose} className="mt-2 text-xs underline">Fechar</button>
    </div>
  )
}
