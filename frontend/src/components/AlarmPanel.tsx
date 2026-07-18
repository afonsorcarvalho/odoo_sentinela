import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

export function AlarmPanel({ alarms }: { alarms: AlarmEvent[] }) {
  const ativos = alarms.filter((a) => a.status !== 'resolvido').length

  return (
    <aside
      className="sticky top-[78px] flex w-full flex-col gap-3 rounded-md p-4 md:w-[300px]"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${ativos > 0 ? 'var(--color-crit)' : 'var(--color-line)'}`,
      }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          Alarmes
        </h2>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-bold"
          style={{
            background: ativos > 0 ? 'var(--color-crit-soft)' : 'var(--color-good-soft)',
            color: ativos > 0 ? 'var(--color-crit)' : 'var(--color-good)',
          }}
        >
          {ativos}
        </span>
      </div>

      {alarms.length === 0 ? (
        <p className="py-6 text-center text-sm" style={{ color: 'var(--color-muted)' }}>
          Nenhum alarme ativo.
        </p>
      ) : (
        <ul className="space-y-2">
          {alarms.map((a) => (
            <AlarmItem key={a.id} alarm={a} />
          ))}
        </ul>
      )}
    </aside>
  )
}
