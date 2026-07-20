import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { FreshnessBadge } from './FreshnessBadge'

describe('FreshnessBadge', () => {
  it('stale: mostra "há N min" em tom de atencao (--color-warn) com icone de relogio', () => {
    render(<FreshnessBadge tier="stale" ageMs={6 * 60_000} />)
    const badge = screen.getByTestId('freshness-badge')
    expect(badge).toHaveTextContent('há 6 min')
    expect(badge.style.color).toBe('var(--color-warn)')
  })

  it('offline com ageMs conhecido: mostra a idade formatada em --color-crit', () => {
    render(<FreshnessBadge tier="offline" ageMs={17 * 60_000} />)
    const badge = screen.getByTestId('freshness-badge')
    expect(badge).toHaveTextContent('há 17 min')
    expect(badge.style.color).toBe('var(--color-crit)')
  })

  it('offline sem ageMs (never escalado, sem ts algum): mostra "offline" em --color-crit', () => {
    render(<FreshnessBadge tier="offline" />)
    const badge = screen.getByTestId('freshness-badge')
    expect(badge).toHaveTextContent('offline')
    expect(badge.style.color).toBe('var(--color-crit)')
  })

  it('never (dentro da graca): rotulo neutro "aguardando dado" em --color-muted, nao "offline"', () => {
    render(<FreshnessBadge tier="never" />)
    const badge = screen.getByTestId('freshness-badge')
    expect(badge).toHaveTextContent('aguardando dado')
    expect(badge.style.color).toBe('var(--color-muted)')
  })
})
