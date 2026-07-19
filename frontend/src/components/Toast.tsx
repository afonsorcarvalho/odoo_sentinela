import type { AlarmEvent } from '../lib/types'

export function Toast({ alarm, areaName, onClose }: { alarm: AlarmEvent; areaName: string; onClose: () => void }) {
  const isResolucao = alarm.status === 'resolvido'
  const color = isResolucao ? 'var(--color-good)' : 'var(--color-crit)'
  const titulo = isResolucao ? `Normalização — ${areaName}` : `Não conformidade — ${areaName}`

  return (
    <div
      role="status"
      className="flex w-[340px] items-start gap-3 rounded-md p-3"
      style={{ background: 'var(--color-surface)', border: `1px solid var(--color-line)`, boxShadow: 'var(--shadow-menu)' }}
    >
      <span className="flex size-[26px] shrink-0 items-center justify-center rounded-full text-xs font-bold" style={{ background: color, color: 'var(--color-surface)' }}>
        !
      </span>
      <div className="flex-1">
        <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>{titulo}</p>
        <p className="text-xs font-medium" style={{ color: 'var(--color-muted)' }}>{alarm.sensor_code}</p>
      </div>
      <button type="button" onClick={onClose} aria-label="Fechar" className="min-h-11 min-w-11 text-lg" style={{ color: 'var(--color-muted)' }}>
        ×
      </button>
    </div>
  )
}
