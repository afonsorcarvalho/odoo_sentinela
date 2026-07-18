import { useParams, Link } from 'react-router'
import { useSensors, useThresholds } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { SensorRow } from '../components/SensorRow'
import { HeaderActions } from '../components/HeaderActions'

function SkeletonRow() {
  return (
    <div
      className="h-16 animate-pulse rounded-xl motion-reduce:animate-none"
      style={{ background: 'var(--color-line)' }}
      aria-hidden="true"
    />
  )
}

export function AreaPage() {
  const { areaCode } = useParams<{ areaCode: string }>()
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const group = groups.find((g) => g.area.area_code === areaCode)
  const ready =
    sensorsQuery.isSuccess &&
    thresholdResults.every((r) => r.isSuccess) &&
    codes.every((c) => liveByCode[c] !== undefined)

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      <div className="mb-2 flex items-center justify-between gap-4">
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-muted)] outline-none transition-colors duration-200 ease-out hover:text-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
        >
          ← Voltar
        </Link>
        <HeaderActions />
      </div>

      {sensorsQuery.isError ? (
        <div
          className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm"
          style={{ color: 'var(--color-crit)' }}
        >
          <span>Falha ao carregar os sensores.</span>
          <button
            type="button"
            className="min-h-11 rounded-md px-3 font-semibold underline outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            onClick={() => sensorsQuery.refetch()}
          >
            Tentar de novo
          </button>
        </div>
      ) : !ready ? (
        <div className="mt-4 space-y-3">
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : !group ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--color-muted)' }}>
          Área não encontrada.
        </p>
      ) : (
        <>
          <header className="mb-6 mt-2">
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
              {group.area.name}
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-muted)' }}>
              {group.area.category}
            </p>
          </header>
          <div className="space-y-3">
            {group.sensors.map((s) => (
              <SensorRow
                key={s.sensor_code}
                sensor={s}
                threshold={thresholdsByCode[s.sensor_code] ?? null}
                live={liveByCode[s.sensor_code]}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
