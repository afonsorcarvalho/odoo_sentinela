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

function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDataResolucao(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function AlarmItem({ alarm, areaName }: { alarm: AlarmEvent; areaName: string }) {
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
        {areaName} · {alarm.sensor_code}
      </p>
      <p className="mt-0.5 text-xs font-medium" style={{ color: 'var(--color-muted)' }}>
        Valor lido {alarm.valor_lido} (limite {alarm.limite_configurado_snapshot})
      </p>
      {alarm.timestamp_resolucao_sensor && (
        <p className="mt-1 text-xs" style={{ color: 'var(--color-muted)' }}>
          Sensor normalizado às {formatTime(alarm.timestamp_resolucao_sensor)}
        </p>
      )}
      {alarm.status === 'resolvido' && alarm.usuario_responsavel && alarm.data_resolucao && (
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-muted)' }}>
          Resolvido por {alarm.usuario_responsavel} em {formatDataResolucao(alarm.data_resolucao)}
        </p>
      )}
      {alarm.observacoes && (
        <p className="mt-0.5 text-xs italic" style={{ color: 'var(--color-muted)' }}>
          "{alarm.observacoes}"
        </p>
      )}
    </li>
  )
}
