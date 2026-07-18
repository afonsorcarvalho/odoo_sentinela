import { useState } from 'react'
import { useSensorMeta, useThreshold, useHistory } from '../lib/queries'
import { useLiveTail } from '../lib/useLiveTail'
import { LiveReadout } from '../components/LiveReadout'
import { WindowSelector } from '../components/WindowSelector'
import { ThresholdBadge } from '../components/ThresholdBadge'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { ThemeToggle } from '../components/ThemeToggle'
import type { Window } from '../lib/types'

// Placeholder de carregamento por painel (nunca um spinner global) — mantem o
// layout final (mesmas dimensoes) para nao pular quando o dado chega.
function SkeletonBlock({ className }: { className: string }) {
  return (
    <div
      className={`animate-pulse rounded-md motion-reduce:animate-none ${className}`}
      style={{ background: 'var(--color-line)' }}
      aria-hidden="true"
    />
  )
}

function ReadoutSkeleton() {
  return (
    <div className="rounded-2xl p-6 md:p-7" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
      <div className="flex items-end gap-2">
        <SkeletonBlock className="h-12 w-28 md:h-14" />
        <SkeletonBlock className="mb-1 h-5 w-8" />
      </div>
      <SkeletonBlock className="mt-4 h-4 w-24" />
      <SkeletonBlock className="mt-6 h-1.5 w-full rounded-full" />
    </div>
  )
}

export function SensorDetailPage({ code }: { code: string }) {
  const [window, setWindow] = useState<Window>('24h')
  const meta = useSensorMeta(code)
  const threshold = useThreshold(code)
  const history = useHistory(code, window)
  const { last, tail } = useLiveTail(code)

  const unidade = meta.data?.unidade ?? ''
  const th = threshold.data ?? null
  const readoutReady = !meta.isLoading && !threshold.isLoading

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          {meta.isLoading ? (
            <SkeletonBlock className="h-7 w-52" />
          ) : (
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
              {meta.data?.name}
            </h1>
          )}
          {meta.isLoading ? (
            <SkeletonBlock className="mt-2 h-4 w-36" />
          ) : (
            meta.data && (
              <p className="mt-1 text-sm" style={{ color: 'var(--color-muted)' }}>
                {meta.data.area.name} · {meta.data.measurement_type.name}
              </p>
            )
          )}
        </div>
        <ThemeToggle />
      </header>

      {/* Instrumento: leitura + tolerancia respondem primeiro (esquerda/topo);
          o grafico e evidencia de apoio (direita/abaixo). Empilha em mobile. */}
      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          {readoutReady ? (
            <>
              <LiveReadout value={last?.value ?? null} unidade={unidade} threshold={th} state={last?.alarm_state} />
              <ThresholdBadge threshold={th} unidade={unidade} />
            </>
          ) : (
            <>
              <ReadoutSkeleton />
              <SkeletonBlock className="h-4 w-40" />
            </>
          )}
        </div>

        <div className="rounded-xl p-4" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
          <div className="mb-4 flex justify-end">
            <WindowSelector value={window} onChange={setWindow} />
          </div>
          {history.isError ? (
            <div className="flex h-80 flex-col items-center justify-center gap-2 text-center text-sm" style={{ color: 'var(--color-crit)' }}>
              <span>Falha ao carregar histórico.</span>
              <button
                type="button"
                className="min-h-11 rounded-md px-3 font-semibold underline outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                onClick={() => history.refetch()}
              >
                Tentar de novo
              </button>
            </div>
          ) : history.isLoading ? (
            <SkeletonBlock className="h-80 w-full" />
          ) : (
            <TimeSeriesChart history={history.data} threshold={th} tail={tail} />
          )}
        </div>
      </div>
    </div>
  )
}
