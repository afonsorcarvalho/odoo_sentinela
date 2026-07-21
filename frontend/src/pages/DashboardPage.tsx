import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSensors, useAlarms, useConfig } from '../lib/queries'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { useAuth } from '../lib/useAuth'
import { useLiveConnection } from '../lib/useLiveConnection'
import { parseLayout } from '../lib/layout/schema'
import { defaultLayout } from '../lib/layout/defaultLayout'
import { DashboardGrid } from '../components/DashboardGrid'
import { DashboardEditor } from '../components/DashboardEditor'
import { Topbar } from '../components/Topbar'
import { ToastContainer } from '../components/ToastContainer'
import { DemoBanner } from '../components/DemoBanner'
import { SensorDetailDrawer } from '../components/SensorDetailDrawer'
import { isDemoMode } from '../lib/demoMode'
import { DrillDownContext } from '../lib/drilldown/DrillDownContext'
import type { AlarmEvent } from '../lib/types'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'

export function DashboardPage() {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const liveState = useLiveConnection()
  const [editing, setEditing] = useState(false)
  const [simulating, setSimulating] = useState(false)
  // null = drawer fechado; string = aberto naquele sensor. A MESMA callback
  // (setSelectedSensorCode) serve dois papeis (ver design doc D3, "Estado e
  // a callback de duplo uso"): abrir via AreaCard (context) e trocar de
  // metrica dentro do SensorDetailDrawer (botao de metrica no painel).
  const [selectedSensorCode, setSelectedSensorCode] = useState<string | null>(null)
  const drillDown = useMemo(() => ({ open: setSelectedSensorCode }), [])

  const sensorsQuery = useSensors()
  const configQuery = useConfig()
  const sensors = sensorsQuery.data ?? []
  const groups = useMemo(() => groupSensorsByArea(sensors), [sensors])
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const alarmsQuery = useAlarms()
  const alarms = alarmsQuery.data ?? []

  // Layout salvo (via /config) tem prioridade; se a config CARREGOU e nao ha
  // layout salvo, cai no default derivado das areas (um card por area + painel
  // de alarmes).
  //
  // IMPORTANTE (regressao "perda de layout no upgrade"): o default so pode
  // aparecer quando a config carregou COM SUCESSO. Enquanto ela esta carregando
  // ou falhou (ex.: o Odoo reinicia a cada `-u` de modulo, deixando o /config
  // momentaneamente indisponivel), NAO renderizamos o default -- senao o
  // operador ve o layout "resetado" (parece perdido, embora o real esteja
  // intacto no DB) e, pior, poderia salva-lo por cima do layout real. Nesses
  // estados mostramos loading/erro+retry e travamos o botao Editar.
  const configReady = configQuery.isSuccess
  const layout = useMemo(
    () => parseLayout(configQuery.data?.layout) ?? defaultLayout(groups),
    [configQuery.data?.layout, groups],
  )

  function simulateAlarm() {
    setSimulating(true)
    const fake: AlarmEvent = {
      id: Date.now(), sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
      tipo_violacao: 'abaixo_limite', status: 'aberto',
      timestamp_deteccao: Date.now(), timestamp_resolucao_sensor: null,
      valor_lido: -1.7, limite_configurado_snapshot: -2.5,
      usuario_responsavel: null, data_resolucao: null, observacoes: null,
    }
    queryClient.setQueryData<AlarmEvent[]>(['alarms'], (old) => [fake, ...(old ?? [])])
  }

  function resetDemo() {
    setSimulating(false)
    queryClient.invalidateQueries({ queryKey: ['alarms'] })
  }

  const healthy = sensorsQuery.isSuccess && !alarmsQuery.isError

  return (
    <div>
      <Topbar healthy={healthy} unitName={UNIT_NAME} liveState={liveState} />
      <ToastContainer alarms={alarms} areaNameByCode={areaNameByCode} loaded={!alarmsQuery.isLoading} />
      {isDemoMode() && <DemoBanner simulating={simulating} onSimulate={simulateAlarm} onReset={resetDemo} />}

      <div className="p-4 sm:p-6">
        <div className="mb-2 flex items-center">
          <p className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-muted)' }}>
            Áreas monitoradas
          </p>
          {isAdmin && !editing && configReady && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="ml-auto rounded border px-3 py-1 text-sm"
              style={{ borderColor: 'var(--color-line-strong)', color: 'var(--color-ink)' }}
            >
              Editar
            </button>
          )}
        </div>

        {configQuery.isError ? (
          // Config falhou (ex.: backend reiniciando pós-upgrade). Nao mostrar
          // o default salvavel — oferecer retry; o layout real segue no DB.
          <div
            className="rounded-md border p-6 text-center"
            style={{ borderColor: 'var(--color-line)', color: 'var(--color-muted)' }}
          >
            <p className="text-sm">
              Não foi possível carregar o layout do dashboard. Seu layout salvo está preservado.
            </p>
            <button
              type="button"
              onClick={() => configQuery.refetch()}
              className="mt-3 rounded px-3 py-1 text-sm font-bold text-white"
              style={{ background: 'var(--color-primary)' }}
            >
              Tentar novamente
            </button>
          </div>
        ) : !configReady ? (
          <div className="p-6 text-center text-sm" style={{ color: 'var(--color-muted)' }}>
            Carregando dashboard…
          </div>
        ) : editing ? (
          <DashboardEditor layout={layout} onExit={() => setEditing(false)} />
        ) : (
          // Provider só no ramo de view: em edição não há DrillDownContext,
          // então AreaWidget cai no no-op (ver design doc D3, "Modo edição
          // vs view") — clicar no valor do card durante edição não abre o
          // drawer, deixa o admin manipular o widget (draggableCancel="button"
          // do DashboardGrid).
          <DrillDownContext.Provider value={drillDown}>
            <DashboardGrid layout={layout} editing={false} />
          </DrillDownContext.Provider>
        )}
      </div>

      {/* Montagem condicional: o SensorDetailDrawer só existe no DOM depois
          que selectedSensorCode vira não-null, ou seja, depois que o clique
          que o abriu (no AreaCard) já terminou de se propagar. O
          useDismiss({ outsidePress: true }) do drawer registra seu listener
          de pointerdown num useEffect, que só roda após esse mount — não há
          como o próprio clique de abertura ser lido como "clique fora" pelo
          listener de uma instância que ainda não existia quando o evento
          disparou. Se o drawer ficasse sempre montado (open controlado só
          por uma prop), o mesmo pointerdown que abre poderia, a depender da
          ordem de effects, ser capturado como outside-press e fechar
          imediatamente — daí a montagem condicional ser estrutural, não
          cosmética. */}
      {selectedSensorCode != null && (
        <SensorDetailDrawer
          sensorCode={selectedSensorCode}
          onSelectSensor={setSelectedSensorCode}
          onClose={() => setSelectedSensorCode(null)}
        />
      )}
    </div>
  )
}
