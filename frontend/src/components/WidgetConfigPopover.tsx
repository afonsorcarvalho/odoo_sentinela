import { useSensors, useThreshold } from '../lib/queries'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WindowSelector } from './WindowSelector'
import { statusTextColor } from './statusVisuals'
import type { WidgetInstance } from '../lib/layout/schema'
import type { Window } from '../lib/types'

const sectionLabelStyle = { color: 'var(--color-muted)' } as const
const selectClass = 'mt-1 block w-full rounded border px-2 py-1 text-xs'
const inputStyle = { borderColor: 'var(--color-muted)' } as const

export function WidgetConfigPopover({ widget, onChange, onClose }: {
  widget: WidgetInstance
  onChange: (w: WidgetInstance) => void
  onClose: () => void
}) {
  const sensors = useSensors().data ?? []
  const needs = WIDGET_REGISTRY[widget.type].needs
  const areas = Array.from(new Map(sensors.map((s) => [s.area.area_code, s.area])).values())
  const scope = (widget.options?.scope as 'site' | 'area' | undefined) ?? 'site'
  // Regra dos hooks: sempre chamado, mesmo sem sensor vinculado ainda (código
  // vazio) ou em widgets que não são kpi. O guard `enabled: code !== ''` vive
  // dentro de useThreshold (lib/queries.ts, espelhando useHistory) — aqui
  // basta chamar; com sensorCode vazio a query fica `idle` (sem request) e
  // `threshold.data` permanece `undefined`, caindo no fallback textual abaixo.
  const threshold = useThreshold(widget.binding.sensorCode ?? '')
  const limiteMinPlaceholder = threshold.data ? String(threshold.data.limite_min) : 'cadastro do sensor'
  const limiteMaxPlaceholder = threshold.data ? String(threshold.data.limite_max) : 'cadastro do sensor'

  // Feedback inline p/ o admin (não bloqueia Salvar — popover não tem Salvar
  // próprio). Espelha o refine de kpiOptions em schema.ts: só reprova quando
  // AMBOS estão preenchidos e min > max; um único campo preenchido é válido.
  const limiteMin = widget.options?.limiteMin as number | undefined
  const limiteMax = widget.options?.limiteMax as number | undefined
  const limitesInvalidos = limiteMin != null && limiteMax != null && limiteMin > limiteMax
  // id sufixado por widget.id: vários popovers podem estar abertos ao mesmo
  // tempo (cada WidgetFrame tem seu próprio estado `open`, sem exclusividade
  // entre widgets) — sem o sufixo, dois KPIs inválidos abertos juntos
  // colidiriam no id e quebrariam o aria-describedby (HTML inválido).
  const limitesErroId = `kpi-limites-erro-${widget.id}`

  // Toda edição flui por onChange (nunca escrita direta no servidor); grava
  // em options fazendo merge com o que já existe, para não perder outras
  // chaves já configuradas.
  function setOption(patch: Record<string, unknown>) {
    onChange({ ...widget, options: { ...widget.options, ...patch } })
  }

  // Mesmo dropdown de área usado pelo binding (needs==='area') é reaproveitado
  // pela config do alarms (scope==='area') — ambos gravam em binding.areaCode.
  const areaSelect = (
    <label className="block text-xs">Área
      <select
        className={selectClass}
        style={inputStyle}
        value={widget.binding.areaCode ?? ''}
        onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, areaCode: e.target.value } })}
      >
        <option value="">—</option>
        {areas.map((a) => <option key={a.area_code} value={a.area_code}>{a.name}</option>)}
      </select>
    </label>
  )

  return (
    <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-muted)' }}>
      <div className="mb-2 text-xs font-bold">{WIDGET_REGISTRY[widget.type].label}</div>

      <div className="mb-1 text-xs font-semibold" style={sectionLabelStyle}>Binding</div>
      {needs === 'area' && areaSelect}
      {needs === 'sensor' && (
        <label className="block text-xs">Sensor
          <select
            className={selectClass}
            style={inputStyle}
            value={widget.binding.sensorCode ?? ''}
            onChange={(e) => onChange({ ...widget, binding: { ...widget.binding, sensorCode: e.target.value } })}
          >
            <option value="">—</option>
            {sensors.map((s) => <option key={s.sensor_code} value={s.sensor_code}>{s.name}</option>)}
          </select>
        </label>
      )}
      {needs === 'none' && (
        <div className="text-xs" style={sectionLabelStyle}>Sem configuração de binding.</div>
      )}

      {widget.type !== 'area' && (
        <>
          <div className="mb-1 mt-3 text-xs font-semibold" style={sectionLabelStyle}>Config</div>

          {widget.type === 'timeseries' && (
            <div className="block text-xs">
              <WindowSelector
                value={(widget.options?.defaultWindow as Window | undefined) ?? '24h'}
                onChange={(w) => setOption({ defaultWindow: w })}
              />
            </div>
          )}

          {widget.type === 'kpi' && (
            <div className="flex flex-col gap-2">
              <label className="block text-xs">Rótulo
                <input
                  type="text"
                  className={selectClass}
                  style={inputStyle}
                  value={(widget.options?.label as string | undefined) ?? ''}
                  onChange={(e) => setOption({ label: e.target.value === '' ? undefined : e.target.value })}
                />
              </label>
              <label className="block text-xs">Limite mín.
                <input
                  type="number"
                  placeholder={limiteMinPlaceholder}
                  className={selectClass}
                  style={inputStyle}
                  value={limiteMin ?? ''}
                  aria-describedby={limitesInvalidos ? limitesErroId : undefined}
                  onChange={(e) => setOption({ limiteMin: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </label>
              <label className="block text-xs">Limite máx.
                <input
                  type="number"
                  placeholder={limiteMaxPlaceholder}
                  className={selectClass}
                  style={inputStyle}
                  value={limiteMax ?? ''}
                  aria-describedby={limitesInvalidos ? limitesErroId : undefined}
                  onChange={(e) => setOption({ limiteMax: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </label>
              {limitesInvalidos && (
                <p id={limitesErroId} role="alert" className="text-xs" style={{ color: statusTextColor('crit') }}>
                  Limite mín. deve ser ≤ limite máx.
                </p>
              )}
            </div>
          )}

          {widget.type === 'alarms' && (
            <div className="flex flex-col gap-2">
              <label className="block text-xs">Escopo
                <select
                  className={selectClass}
                  style={inputStyle}
                  value={scope}
                  onChange={(e) => setOption({ scope: e.target.value })}
                >
                  <option value="site">Site</option>
                  <option value="area">Área</option>
                </select>
              </label>
              {scope === 'area' && areaSelect}
            </div>
          )}
        </>
      )}

      <button type="button" onClick={onClose} className="mt-2 text-xs underline">Fechar</button>
    </div>
  )
}
