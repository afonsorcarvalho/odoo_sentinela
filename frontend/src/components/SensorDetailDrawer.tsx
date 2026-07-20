import { useState } from 'react'
import { useFloating, useDismiss, useInteractions, FloatingFocusManager, FloatingPortal, FloatingOverlay } from '@floating-ui/react'
import { useSensors, useThreshold, useHistory } from '../lib/queries'
import { useLiveTail } from '../lib/useLiveTail'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { SensorDetailPanel } from './SensorDetailPanel'
import type { Window } from '../lib/types'

// Container que religa o SensorDetailPanel (puramente apresentacional) num
// drill-down: fecha os hooks de dados a partir de um sensorCode e apresenta
// o painel dentro de um drawer lateral direito com a11y (role=dialog,
// aria-modal, focus trap, Esc/backdrop/✕ fecham). Mesmo padrao de wiring do
// TimeseriesWidget.tsx, acrescido dos campos de leitura que SensorDetailPanel
// exige (ver design doc D3, "Como o painel recebe o sensor selecionado").
//
// selectedSensorCode e o setter moram na DashboardPage (T3) -- aqui so
// recebemos o code atual + callbacks. A MESMA onSelectSensor serve dois
// papeis: quem monta este componente decide o que "abrir"/"trocar" significa;
// aqui so garantimos que o botao de metrica dentro do painel a chama.
//
// Altura (DT/M2): o drawer e h-screen (define altura), flex-col, com uma
// linha de cabecalho (✕) em altura natural e o SensorDetailPanel dentro de
// um wrapper min-h-0 flex-1 -- o painel por si so ja e h-full flex-col com o
// chart embrulhado em min-h-0 flex-1 (T1), entao a cadeia de altura definida
// chega ate o TimeSeriesChart.
export function SensorDetailDrawer({
  sensorCode,
  onSelectSensor,
  onClose,
}: {
  sensorCode: string
  onSelectSensor: (code: string) => void
  onClose: () => void
}) {
  const [window, setWindow] = useState<Window>('24h')

  // Sem elemento de referencia (trigger) neste escopo -- quem abre o drawer
  // e o AreaCard, em outro componente (T3). Focus trap + Esc + backdrop
  // funcionam sem reference; a restauracao de foco ao botao de origem do
  // AreaCard e validada na integracao (T3), nao aqui.
  const { context, refs } = useFloating({
    open: true,
    onOpenChange: (open) => {
      if (!open) onClose()
    },
  })
  // outsidePress fecha ao clicar no backdrop. Importante: o backdrop (via
  // FloatingOverlay abaixo) precisa ser ANCESTRAL do elemento floating, nao
  // irmao -- com FloatingFocusManager modal (default), tudo que fica FORA da
  // arvore do floating vira inert (markOthers) em navegador real, entao um
  // backdrop irmao com onClick manual nunca receberia o clique (jsdom nao
  // implementa `inert`, entao esse bug passaria despercebido nos testes).
  // outsidePress do floating-ui reconhece explicitamente esse padrao
  // "clicou num ancestral direto (FloatingOverlay)" como fora do floating.
  const dismiss = useDismiss(context, { outsidePress: true, escapeKey: true })
  const { getFloatingProps } = useInteractions([dismiss])

  const sensors = useSensors().data ?? []
  const group = groupSensorsByArea(sensors).find((g) =>
    g.sensors.some((s) => s.sensor_code === sensorCode),
  )
  const sensor = sensors.find((s) => s.sensor_code === sensorCode)
  const threshold = useThreshold(sensorCode).data ?? null
  const history = useHistory(sensorCode, window).data
  const { last, tail } = useLiveTail(sensorCode)
  const value = last?.value ?? null
  const state = last?.alarm_state

  if (!group || !sensor) return null

  return (
    <FloatingPortal>
      {/* FloatingOverlay como ANCESTRAL do floating (nao irmao) -- ver
          comentario acima do useDismiss. z-40 fica atras do drawer (z-50). */}
      <FloatingOverlay
        data-testid="sensor-detail-drawer-backdrop"
        lockScroll
        className="z-40"
        style={{ background: 'rgb(0 0 0 / 0.5)' }}
      >
        <FloatingFocusManager context={context}>
          <div
            ref={refs.setFloating}
            role="dialog"
            aria-modal="true"
            aria-label={`Detalhe do sensor ${sensor.name}`}
            className="fixed right-0 top-0 z-50 flex h-screen flex-col"
            style={{ width: 'min(560px, 100vw)', background: 'var(--color-surface)', boxShadow: 'var(--shadow-menu)' }}
            {...getFloatingProps()}
          >
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={onClose}
                aria-label="Fechar"
                className="min-h-11 min-w-11 rounded-md text-lg font-semibold outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                style={{ color: 'var(--color-muted)' }}
              >
                ✕
              </button>
            </div>
            <div className="min-h-0 flex-1 px-3 pb-3">
              <SensorDetailPanel
                group={group}
                selectedCode={sensorCode}
                onSelectSensor={onSelectSensor}
                threshold={threshold}
                unidade={sensor.unidade}
                value={value}
                state={state}
                window={window}
                onWindowChange={setWindow}
                history={history}
                tail={tail}
              />
            </div>
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
