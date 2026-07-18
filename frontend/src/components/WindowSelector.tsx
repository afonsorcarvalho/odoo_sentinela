import type { Window } from '../lib/types'

const WINDOWS: Window[] = ['1h', '24h', '7d', '30d']

// Cor de texto do chip ativo: --color-surface tem exatamente a polaridade
// necessária (quase-branco no tema claro, quase-preto no tema escuro) para
// permanecer legível sobre --color-primary nos dois temas — --color-primary
// muda de L=0.55 (claro) para L=0.70 (escuro), e texto branco fixo cai para
// ~2.6:1 no escuro. Verificado por script (OKLCH->sRGB completo): 4.81:1
// claro, 6.70:1 escuro — ambos acima do mínimo de 4.5:1.
export function WindowSelector({
  value,
  onChange,
}: {
  value: Window
  onChange: (w: Window) => void
}) {
  return (
    <div
      className="inline-flex gap-1 rounded-lg p-1"
      style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)' }}
      role="group"
      aria-label="Janela temporal"
    >
      {WINDOWS.map((w) => {
        const on = w === value
        return (
          <button
            key={w}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(w)}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-md px-3.5 py-2 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
            style={
              on
                ? { background: 'var(--color-primary)', color: 'var(--color-surface)' }
                : { color: 'var(--color-muted)' }
            }
          >
            {w}
          </button>
        )
      })}
    </div>
  )
}
