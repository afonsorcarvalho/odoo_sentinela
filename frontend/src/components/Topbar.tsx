import { BrandMark } from './BrandMark'
import { NavLink } from 'react-router'
import { ThemeToggle } from './ThemeToggle'
import { LogoutButton } from './LogoutButton'
import { LiveClock } from './LiveClock'
import type { LiveConnectionState } from '../lib/types'

// Mapeia estado de conexao -> apresentacao do badge. Topbar e apresentacional
// (ver design doc A3): so traduz o LiveConnectionState recebido por prop, sem
// logica de EventSource/timer aqui. `dotClassName` distingue os 3 estados no
// ponto: live pulsa cheio; reconnecting pulsa mas opaco ("pulso lento/opaco"
// no design doc); offline e estatico (sem animate-pulse), terminal.
const LIVE_STATE_BADGE: Record<LiveConnectionState, { label: string; color: string; dotClassName: string }> = {
  live: { label: 'AO VIVO', color: 'var(--color-good)', dotClassName: 'motion-safe:animate-pulse' },
  reconnecting: { label: 'Reconectando…', color: 'var(--color-warn)', dotClassName: 'motion-safe:animate-pulse opacity-70' },
  offline: { label: 'Sem conexão', color: 'var(--color-crit)', dotClassName: '' },
}

export function Topbar({
  healthy,
  unitName,
  liveState,
}: {
  healthy: boolean
  unitName: string
  liveState: LiveConnectionState
}) {
  const badge = LIVE_STATE_BADGE[liveState]
  return (
    <header
      className="sticky top-0 z-10 flex flex-wrap items-center gap-4 gap-y-2 px-6 py-3"
      style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-line)' }}
    >
      <div className="flex items-center gap-2">
        <BrandMark />
        <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
          Sentinela
        </span>
        <span className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
          CME
        </span>
      </div>

      <span
        className="min-w-0 max-w-[200px] truncate rounded-full px-3 py-1 text-sm font-semibold"
        style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', color: 'var(--color-ink)' }}
      >
        {unitName}
      </span>

      <nav aria-label="Principal" className="flex items-center gap-1 text-sm font-semibold">
        {[
          { to: '/', label: 'Painel' },
          { to: '/relatorios', label: 'Relatórios' },
        ].map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end
            className="rounded-md px-3 py-1.5 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
            style={({ isActive }) => ({
              color: isActive ? 'var(--color-primary)' : 'var(--color-muted)',
              background: isActive ? 'var(--color-panel)' : undefined,
            })}
          >
            {l.label}
          </NavLink>
        ))}
      </nav>

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

        <span
          role="status"
          aria-live="polite"
          className="flex items-center gap-1.5 text-xs font-bold tracking-wide"
          style={{ color: badge.color }}
        >
          <span
            aria-hidden="true"
            className={`size-[9px] rounded-full${badge.dotClassName ? ` ${badge.dotClassName}` : ''}`}
            style={{ background: badge.color }}
          />
          {badge.label}
        </span>

        <ThemeToggle />
        <LogoutButton />
      </div>
    </header>
  )
}
