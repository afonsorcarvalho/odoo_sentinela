import { ThemeToggle } from './ThemeToggle'
import { LogoutButton } from './LogoutButton'
import { LiveClock } from './LiveClock'

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
    </svg>
  )
}

export function Topbar({ healthy, unitName }: { healthy: boolean; unitName: string }) {
  return (
    <header
      className="sticky top-0 z-10 flex items-center gap-4 px-6 py-3"
      style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-line)' }}
    >
      <div className="flex items-center gap-2">
        <div
          className="flex size-[34px] items-center justify-center rounded-md"
          style={{ background: 'var(--color-primary)', color: 'var(--color-surface)' }}
        >
          <ShieldIcon />
        </div>
        <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
          Sentinela
        </span>
        <span className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
          CME
        </span>
      </div>

      <span
        className="rounded-full px-3 py-1 text-sm font-semibold"
        style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', color: 'var(--color-ink)' }}
      >
        {unitName}
      </span>

      <div className="ml-auto flex items-center gap-3">
        {healthy && (
          <span
            className="rounded-md px-3 py-1.5 text-sm font-bold"
            style={{ background: 'var(--color-good-soft)', color: 'var(--color-good)' }}
          >
            Registro íntegro
          </span>
        )}

        <LiveClock />

        <span className="flex items-center gap-1.5 text-xs font-bold tracking-wide" style={{ color: 'var(--color-good)' }}>
          <span
            aria-hidden="true"
            className="size-[9px] rounded-full motion-safe:animate-pulse"
            style={{ background: 'var(--color-good)' }}
          />
          AO VIVO
        </span>

        <ThemeToggle />
        <LogoutButton />
      </div>
    </header>
  )
}
