import { useSensors, useThresholds } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { AreaCard } from '../components/AreaCard'
import { ThemeToggle } from '../components/ThemeToggle'

function SkeletonCard() {
  return (
    <div
      className="h-28 animate-pulse rounded-2xl motion-reduce:animate-none"
      style={{ background: 'var(--color-line)' }}
      aria-hidden="true"
    />
  )
}

export function OverviewPage() {
  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const ready = sensorsQuery.isSuccess && thresholdResults.every((r) => r.isSuccess)

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6">
      <header className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
          Visão geral
        </h1>
        <ThemeToggle />
      </header>

      {sensorsQuery.isError ? (
        <div
          className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm"
          style={{ color: 'var(--color-crit)' }}
        >
          <span>Falha ao carregar as áreas.</span>
          <button
            type="button"
            className="min-h-11 rounded-md px-3 font-semibold underline outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            onClick={() => sensorsQuery.refetch()}
          >
            Tentar de novo
          </button>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {!ready
            ? Array.from({ length: 3 }, (_, i) => <SkeletonCard key={i} />)
            : groups.map((g) => (
                <AreaCard key={g.area.area_code} group={g} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode} />
              ))}
        </div>
      )}
    </div>
  )
}
