import { useEffect, useState } from 'react'
import { usePrefersReducedMotion } from '../lib/useSensorCarousel'

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
  // Control (escuro) e o tema padrao recomendado p/ monitoramento continuo —
  // nao segue mais prefers-color-scheme do SO.
  const [control, setControl] = useState(true)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    document.documentElement.classList.toggle('theme-control', control)
  }, [control])

  return (
    <button
      type="button"
      onClick={() => setControl((c) => !c)}
      className="flex min-h-11 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
      aria-pressed={control}
      aria-label={control ? 'Trocar para tema claro' : 'Trocar para tema escuro'}
    >
      <span
        key={control ? 'sun' : 'moon'}
        className="inline-flex motion-reduce:animate-none"
        style={{ animation: reducedMotion ? undefined : 'icon-swap var(--dur-base) var(--ease-overshoot)' }}
      >
        {control ? <SunIcon /> : <MoonIcon />}
      </span>
      <span>{control ? 'Claro' : 'Escuro'}</span>
    </button>
  )
}
