import { useEffect, useState } from 'react'
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

function matchesQuery(alarm: AlarmEvent, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return alarm.sensor_code.toLowerCase().includes(q) || alarm.area.name.toLowerCase().includes(q)
}

function localDateString(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function matchesDate(alarm: AlarmEvent, date: string): boolean {
  if (!date) return true
  return localDateString(alarm.timestamp_deteccao) === date
}

export function AlarmsModal({ alarms, onClose }: { alarms: AlarmEvent[]; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [date, setDate] = useState('')

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const filtrados = alarms.filter((a) => matchesQuery(a, query) && matchesDate(a, date))

  return (
    <div
      data-testid="alarms-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgb(0 0 0 / 0.5)' }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Todos os alarmes"
        className="flex max-h-[80vh] w-full max-w-lg flex-col gap-3 rounded-md p-4"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
            Todos os alarmes
          </h2>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-md text-xl outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ color: 'var(--color-muted)' }}
          >
            ×
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Buscar por sensor ou área"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-h-11 flex-1 rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', color: 'var(--color-ink)' }}
          />
          <label className="flex min-h-11 items-center gap-2 rounded-md px-3 text-sm" style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}>
            Data
            <input
              type="date"
              aria-label="Data"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-transparent text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
              style={{ color: 'var(--color-ink)' }}
            />
          </label>
        </div>

        {filtrados.length === 0 ? (
          <p className="py-6 text-center text-sm" style={{ color: 'var(--color-muted)' }}>
            Nenhum alarme encontrado.
          </p>
        ) : (
          <ul className="space-y-2 overflow-y-auto">
            {filtrados.map((a) => (
              <AlarmItem key={a.id} alarm={a} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
