import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSensors, useAlarms, useConfig } from '../lib/queries'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { useAuth } from '../lib/useAuth'
import { parseLayout } from '../lib/layout/schema'
import { defaultLayout } from '../lib/layout/defaultLayout'
import { DashboardGrid } from '../components/DashboardGrid'
import { DashboardEditor } from '../components/DashboardEditor'
import { Topbar } from '../components/Topbar'
import { AlarmsModal } from '../components/AlarmsModal'
import { ToastContainer } from '../components/ToastContainer'
import { DemoBanner } from '../components/DemoBanner'
import { isDemoMode } from '../lib/demoMode'
import type { AlarmEvent } from '../lib/types'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'

export function DashboardPage() {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [simulating, setSimulating] = useState(false)
  const [alarmsModalOpen, setAlarmsModalOpen] = useState(false)

  const sensorsQuery = useSensors()
  const configQuery = useConfig()
  const sensors = sensorsQuery.data ?? []
  const groups = groupSensorsByArea(sensors)
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const alarmsQuery = useAlarms()
  const alarms = alarmsQuery.data ?? []

  // Layout salvo (via /config) tem prioridade; se ausente ou invalido, cai no
  // default derivado das areas (um card por area + painel de alarmes).
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
      <Topbar healthy={healthy} unitName={UNIT_NAME} />
      <ToastContainer alarms={alarms} areaNameByCode={areaNameByCode} loaded={!alarmsQuery.isLoading} />
      {isDemoMode() && <DemoBanner simulating={simulating} onSimulate={simulateAlarm} onReset={resetDemo} />}

      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="mb-2 flex items-center">
          <p className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-muted)' }}>
            Áreas monitoradas
          </p>
          {isAdmin && !editing && (
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

        {editing ? (
          <DashboardEditor layout={layout} onExit={() => setEditing(false)} />
        ) : (
          <DashboardGrid layout={layout} editing={false} />
        )}
      </div>

      {alarmsModalOpen && (
        <AlarmsModal alarms={alarms} areaNameByCode={areaNameByCode} onClose={() => setAlarmsModalOpen(false)} />
      )}
    </div>
  )
}
