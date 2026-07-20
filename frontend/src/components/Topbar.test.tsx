import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { Topbar } from './Topbar'

function wrap(node: React.ReactNode) {
  return (
    <MemoryRouter>
      <AuthProvider>{node}</AuthProvider>
    </MemoryRouter>
  )
}

describe('Topbar', () => {
  it('mostra a marca, o nome da unidade e o indicador AO VIVO', () => {
    render(wrap(<Topbar healthy unitName="Hospital Demonstração" liveState="live" />))
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
    expect(screen.getByText('CME')).toBeInTheDocument()
    expect(screen.getByText('Hospital Demonstração')).toBeInTheDocument()
    expect(screen.getByText('AO VIVO')).toBeInTheDocument()
  })

  it('healthy=true mostra "Registro íntegro"; healthy=false nao mostra', () => {
    const { rerender } = render(wrap(<Topbar healthy unitName="X" liveState="live" />))
    expect(screen.getByText('Registro íntegro')).toBeInTheDocument()

    rerender(wrap(<Topbar healthy={false} unitName="X" liveState="live" />))
    expect(screen.queryByText('Registro íntegro')).not.toBeInTheDocument()
  })

  it('header permite quebra de linha em telas estreitas (flex-wrap)', () => {
    render(wrap(<Topbar healthy unitName="X" liveState="live" />))
    expect(screen.getByText('Sentinela').closest('header')).toHaveClass('flex-wrap')
  })

  it('liveState=live mostra "AO VIVO" na cor --color-good, com ponto pulsante', () => {
    render(wrap(<Topbar healthy unitName="X" liveState="live" />))
    const badge = screen.getByText('AO VIVO')
    expect(badge.closest('span[role="status"]')).toHaveStyle({ color: 'var(--color-good)' })
    const dot = badge.parentElement?.querySelector('[aria-hidden="true"]')
    expect(dot?.className).toContain('motion-safe:animate-pulse')
  })

  it('liveState=reconnecting mostra "Reconectando…" na cor --color-warn', () => {
    render(wrap(<Topbar healthy unitName="X" liveState="reconnecting" />))
    const badge = screen.getByText('Reconectando…')
    expect(badge.closest('span[role="status"]')).toHaveStyle({ color: 'var(--color-warn)' })
  })

  it('liveState=offline mostra "Sem conexão" na cor --color-crit', () => {
    render(wrap(<Topbar healthy unitName="X" liveState="offline" />))
    const badge = screen.getByText('Sem conexão')
    expect(badge.closest('span[role="status"]')).toHaveStyle({ color: 'var(--color-crit)' })
  })

  it('badge de conexao expoe role="status" e aria-live="polite"', () => {
    render(wrap(<Topbar healthy unitName="X" liveState="live" />))
    const badge = screen.getByText('AO VIVO').closest('span[role="status"]')
    expect(badge).toHaveAttribute('aria-live', 'polite')
  })
})
