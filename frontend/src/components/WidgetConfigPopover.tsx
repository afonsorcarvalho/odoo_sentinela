import { useThreshold } from '../lib/queries'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WindowSelector } from './WindowSelector'
import { statusTextColor } from './statusVisuals'
import { AreaSelect } from './select/AreaSelect'
import { SensorSelect } from './select/SensorSelect'
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
  const needs = WIDGET_REGISTRY[widget.type].needs
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
  // id sufixado por widget.id: mantém o aria-describedby único por widget. Hoje
  // só há um drawer de config aberto por vez, mas o sufixo é barato e à prova de
  // futuro (ex.: comparação lado a lado) — sem ele, dois KPIs inválidos no mesmo
  // DOM colidiriam no id (HTML inválido).
  const limitesErroId = `kpi-limites-erro-${widget.id}`

  // Toda edição flui por onChange (nunca escrita direta no servidor); grava
  // em options fazendo merge com o que já existe, para não perder outras
  // chaves já configuradas.
  function setOption(patch: Record<string, unknown>) {
    onChange({ ...widget, options: { ...widget.options, ...patch } })
  }

  // Combobox pesquisável de área, usado pelo binding de widgets needs==='area'
  // (tipo 'area'). Grava em binding.areaCode (single) — não confundir com o
  // multi-área do alarms logo abaixo, que é outro caminho de escrita
  // (binding.areaCodes).
  const areaSelect = (
    <AreaSelect
      label="Área"
      value={widget.binding.areaCode ?? null}
      onChange={(code) => onChange({ ...widget, binding: { ...widget.binding, areaCode: code ?? undefined } })}
    />
  )

  // Multi-área do alarms (scope==='area'): combobox multi (chips + Pesquisar
  // mais), gravando em binding.areaCodes. Regra de resolução p/ exibição
  // (mesma do registry): areaCodes ?? (areaCode ? [areaCode] : []) — cobre
  // widget legado que só tem binding.areaCode. Na primeira edição
  // (add/remove), passa a gravar em areaCodes; o areaCode legado, se houver,
  // fica como está (não é limpo — a resolução no registry já prefere
  // areaCodes quando presente).
  const areaCodesEfetivos = widget.binding.areaCodes ?? (widget.binding.areaCode ? [widget.binding.areaCode] : [])
  const alarmsAreaSection = (
    <AreaSelect
      multiple
      label="Áreas"
      value={areaCodesEfetivos}
      onChange={(codes) => onChange({ ...widget, binding: { ...widget.binding, areaCodes: codes } })}
    />
  )

  return (
    // Container sem chrome de cartão: hoje este corpo é renderizado dentro do
    // WidgetConfigDrawer (aba lateral), cuja .drawer-panel já é a superfície.
    // Um border/bg próprio aqui viraria cartão-dentro-de-cartão.
    <div>
      <div className="mb-2 text-xs font-bold">{WIDGET_REGISTRY[widget.type].label}</div>

      <div className="mb-1 text-xs font-semibold" style={sectionLabelStyle}>Binding</div>
      {needs === 'area' && areaSelect}
      {needs === 'sensor' && (
        <SensorSelect
          label="Sensor"
          value={widget.binding.sensorCode ?? null}
          onChange={(code) => onChange({ ...widget, binding: { ...widget.binding, sensorCode: code ?? undefined } })}
        />
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
              <label className="block text-xs">Dígitos inteiros (mín.)
                <input
                  type="number"
                  min={1}
                  max={12}
                  placeholder="auto"
                  className={selectClass}
                  style={inputStyle}
                  value={(widget.options?.digitosInteiros as number | undefined) ?? ''}
                  onChange={(e) => setOption({ digitosInteiros: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </label>
              <label className="block text-xs">Casas decimais
                <input
                  type="number"
                  min={0}
                  max={6}
                  placeholder="auto"
                  className={selectClass}
                  style={inputStyle}
                  value={(widget.options?.casasDecimais as number | undefined) ?? ''}
                  onChange={(e) => setOption({ casasDecimais: e.target.value === '' ? undefined : Number(e.target.value) })}
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
              {scope === 'area' && alarmsAreaSection}
            </div>
          )}
        </>
      )}

      <button type="button" onClick={onClose} className="mt-2 text-xs underline">Fechar</button>
    </div>
  )
}
