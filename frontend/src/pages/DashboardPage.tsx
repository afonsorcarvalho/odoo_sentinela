import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useSensors, useThresholds, useHistory, useAlarms, useConfig } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { useLiveTail } from '../lib/useLiveTail'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { AreaCard } from '../components/AreaCard'
import { Topbar } from '../components/Topbar'
import { AlarmPanel } from '../components/AlarmPanel'
import { AlarmsModal } from '../components/AlarmsModal'
import { ToastContainer } from '../components/ToastContainer'
import { SensorDetailPanel } from '../components/SensorDetailPanel'
import { DemoBanner } from '../components/DemoBanner'
import { isDemoMode } from '../lib/demoMode'
import type { Window, AlarmEvent } from '../lib/types'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'

function isToday(ts: number): boolean {
  const d = new Date(ts)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
}

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [window, setWindow] = useState<Window>('24h')
  const queryClient = useQueryClient()
  const [simulating, setSimulating] = useState(false)
  const [alarmsModalOpen, setAlarmsModalOpen] = useState(false)

  const sensorsQuery = useSensors()
  const configQuery = useConfig()
  const carouselIntervalMs = configQuery.data?.carousel_interval_ms ?? 3000
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const alarmsQuery = useAlarms()
  const alarms = alarmsQuery.data ?? []

  const areaParam = searchParams.get('area')
  const sensorParam = searchParams.get('sensor')
  const selectedGroup =
    groups.find((g) => g.sensors.some((s) => s.sensor_code === sensorParam))
    ?? groups.find((g) => g.area.area_code === areaParam)
    ?? groups[0]
  const selectedCode =
    selectedGroup?.sensors.find((s) => s.sensor_code === sensorParam)?.sensor_code
    ?? selectedGroup?.sensors[0]?.sensor_code
    ?? null

  const history = useHistory(selectedCode ?? '', window)
  const { last, tail } = useLiveTail(selectedCode ?? '')

  function selectSensor(code: string) {
    const group = groups.find((g) => g.sensors.some((s) => s.sensor_code === code))
    setSearchParams(group ? { area: group.area.area_code, sensor: code } : { sensor: code })
  }

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

  const ready = sensorsQuery.isSuccess && thresholdResults.every((r) => r.isSuccess)
  const healthy = sensorsQuery.isSuccess && !alarmsQuery.isError

  return (
    <div>
      <Topbar healthy={healthy} unitName={UNIT_NAME} />
      <ToastContainer alarms={alarms} areaNameByCode={areaNameByCode} loaded={!alarmsQuery.isLoading} />
      {isDemoMode() && <DemoBanner simulating={simulating} onSimulate={simulateAlarm} onReset={resetDemo} />}

      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <p className="mb-2 text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-muted)' }}>
          Áreas monitoradas
        </p>

        <div className="flex flex-wrap gap-6">
          <div className="flex-1" style={{ minWidth: 280 }}>
            {!ready ? (
              <p className="text-sm" style={{ color: 'var(--color-muted)' }}>Carregando…</p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(232px, 1fr))' }}>
                {groups.map((g) => (
                  <AreaCard
                    key={g.area.area_code}
                    group={g}
                    thresholdsByCode={thresholdsByCode}
                    liveByCode={liveByCode}
                    selectedSensorCode={selectedCode}
                    onSelectSensor={selectSensor}
                    hadAlarmToday={alarms.some((a) => a.area_code === g.area.area_code && isToday(a.timestamp_deteccao))}
                    carouselIntervalMs={carouselIntervalMs}
                  />
                ))}
              </div>
            )}

            {ready && selectedGroup && selectedCode && (
              <div className="mt-6">
                <SensorDetailPanel
                  group={selectedGroup}
                  selectedCode={selectedCode}
                  onSelectSensor={selectSensor}
                  threshold={thresholdsByCode[selectedCode] ?? null}
                  unidade={selectedGroup.sensors.find((s) => s.sensor_code === selectedCode)?.unidade ?? ''}
                  value={last?.value ?? null}
                  state={last?.alarm_state}
                  window={window}
                  onWindowChange={setWindow}
                  history={history.data}
                  tail={tail}
                />
              </div>
            )}
          </div>

          <AlarmPanel alarms={alarms} areaNameByCode={areaNameByCode} onVerMais={() => setAlarmsModalOpen(true)} />
        </div>
      </div>

      {alarmsModalOpen && <AlarmsModal alarms={alarms} areaNameByCode={areaNameByCode} onClose={() => setAlarmsModalOpen(false)} />}
    </div>
  )
}
