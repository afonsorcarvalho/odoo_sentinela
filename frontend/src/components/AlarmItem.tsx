import type { AlarmEvent } from '../lib/types'

const TIPO_LABEL: Record<AlarmEvent['status'], string> = {
  aberto: 'NÃO CONFORMIDADE',
  reconhecido: 'NÃO CONFORMIDADE',
  resolvido: 'NORMALIZAÇÃO',
}
const BORDER_COLOR: Record<AlarmEvent['status'], string> = {
  aberto: 'var(--color-crit)',
  reconhecido: 'var(--color-crit)',
  resolvido: 'var(--color-good)',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function AlarmItem({ alarm }: { alarm: AlarmEvent }) {
  return (
    <li
      className="rounded-md p-3"
      style={{ background: 'var(--color-panel)', borderLeft: `3px solid ${BORDER_COLOR[alarm.status]}` }}
    >
      <div className="flex items-center justify-between gap-2 text-xs font-bold" style={{ color: BORDER_COLOR[alarm.status] }}>
        <span>{TIPO_LABEL[alarm.status]}</span>
        <span className="font-mono" style={{ color: 'var(--color-muted)' }}>{formatTime(alarm.timestamp_deteccao)}</span>
      </div>
      <p className="mt-1 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
        {alarm.area.name} · {alarm.sensor_code}
      </p>
      <p className="mt-0.5 text-xs font-medium" style={{ color: 'var(--color-muted)' }}>
        Valor lido {alarm.valor_lido ?? '—'} (limite {alarm.limite_configurado_snapshot ?? '—'})
      </p>
    </li>
  )
}
