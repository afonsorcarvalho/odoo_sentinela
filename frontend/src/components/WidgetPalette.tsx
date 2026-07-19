import { useState } from 'react'
import { WIDGET_REGISTRY } from '../lib/widgets/registry'
import { WIDGET_TYPES } from '../lib/layout/schema'
import type { WidgetType } from '../lib/layout/schema'

export function WidgetPalette({ onAdd }: { onAdd: (type: WidgetType) => void }) {
  const [open, setOpen] = useState(false)

  function handlePick(t: WidgetType) {
    onAdd(t)
    setOpen(false)
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="rounded px-3 py-1 text-sm font-bold text-white"
        style={{ background: 'var(--color-primary)' }}
      >
        + Adicionar
      </button>
      {open && (
        <div
          className="absolute left-0 top-full z-20 mt-1 flex flex-col gap-1 rounded-lg border p-2 shadow-lg"
          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-muted)' }}
        >
          {WIDGET_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => handlePick(t)}
              className="rounded border px-2 py-1 text-left text-xs whitespace-nowrap"
              style={{ borderColor: 'var(--color-muted)' }}
            >
              + {WIDGET_REGISTRY[t].label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
