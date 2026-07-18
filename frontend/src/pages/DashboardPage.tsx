import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useSensors, useThresholds, useHistory, useAlarms } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { useLiveTail } from '../lib/useLiveTail'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { AreaCard } from '../components/AreaCard'
import { Topbar } from '../components/Topbar'
import { AlarmPanel } from '../components/AlarmPanel'
import { ToastContainer } from '../components/ToastContainer'
import { SensorDetailPanel } from '../components/SensorDetailPanel'
import type { Window } from '../lib/types'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'

function isToday(iso: string): boolean {
  return iso.slice(0, 10) === new Date().toISOString().slice(0, 10)
}

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [window, setWindow] = useState<Window>('24h')

  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
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

  const ready = sensorsQuery.isSuccess && thresholdResults.every((r) => r.isSuccess)
  const healthy = sensorsQuery.isSuccess && !alarmsQuery.isError

  return (
    <div>
      <Topbar healthy={healthy} unitName={UNIT_NAME} />
      <ToastContainer alarms={alarms} loaded={!alarmsQuery.isLoading} />

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
                    hadAlarmToday={alarms.some((a) => a.area.area_code === g.area.area_code && isToday(a.timestamp_deteccao))}
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

          <AlarmPanel alarms={alarms} />
        </div>
      </div>
    </div>
  )
}
