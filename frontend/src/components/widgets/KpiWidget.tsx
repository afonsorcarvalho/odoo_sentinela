import { useSensorMeta } from '../../lib/queries'
import { useLiveTail } from '../../lib/useLiveTail'
import { statusTextColor } from '../statusVisuals'
import type { StatusResult } from '../../lib/status'

type State = StatusResult['state']

// KPI: valor atual (live) de 1 sensor em destaque, cor por estado de alarme.
export function KpiWidget({ sensorCode, label }: { sensorCode: string; label?: string }) {
  const meta = useSensorMeta(sensorCode)
  const { last } = useLiveTail(sensorCode)
  const titulo = label ?? meta.data?.name ?? sensorCode
  const unidade = meta.data?.unidade ?? ''
  const state: State = last?.alarm_state ?? 'unknown'
  // Mesma convenção do AreaCard: ok/unknown usam --color-ink (contraste
  // padrão); apenas warn/crit usam o token de cor de estado.
  const cor = state === 'ok' || state === 'unknown' ? 'var(--color-ink)' : statusTextColor(state)

  return (
    <div
      className="flex h-full flex-col justify-between rounded-lg p-3"
      style={{ background: 'var(--color-surface)' }}
    >
      <p
        className="truncate text-xs font-bold uppercase tracking-wide"
        style={{ color: 'var(--color-muted)' }}
      >
        {titulo}
      </p>
      <div className="flex items-baseline gap-1">
        {/* Fonte fluida via container query: escala com a largura do card
            (WidgetFrame e @container), nao da viewport. */}
        <span className="font-bold tabular-nums text-[clamp(1.25rem,8cqw,2.25rem)]" style={{ color: cor }}>
          {last?.value ?? '—'}
        </span>
        <span className="text-sm" style={{ color: 'var(--color-muted)' }}>
          {unidade}
        </span>
      </div>
    </div>
  )
}
