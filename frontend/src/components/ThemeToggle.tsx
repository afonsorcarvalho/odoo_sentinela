import { useEffect, useState } from 'react'

function prefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

// Sol/lua minimalistas — mesmo peso visual dos ícones de status do readout
// (stroke-based, 16x16 viewBox), para não introduzir um segundo vocabulário
// gráfico na página.
function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="8" cy="8" r="3.4" />
      <path
        strokeLinecap="round"
        d="M8 1.2v1.6M8 13.2v1.6M14.8 8h-1.6M2.8 8H1.2M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1M12.7 12.7l-1.1-1.1M4.4 4.4 3.3 3.3"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M13.6 10.2A6 6 0 0 1 5.8 2.4a6.4 6.4 0 1 0 7.8 7.8Z" />
    </svg>
  )
}

export function ThemeToggle() {
  const [dark, setDark] = useState(prefersDark)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  return (
    <button
      type="button"
      onClick={() => setDark((d) => !d)}
      className="flex min-h-11 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
      aria-pressed={dark}
      aria-label={dark ? 'Trocar para tema claro' : 'Trocar para tema escuro'}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
      <span>{dark ? 'Claro' : 'Escuro'}</span>
    </button>
  )
}
