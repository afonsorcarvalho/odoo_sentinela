import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, afterEach, vi } from 'vitest'
import { ThemeToggle } from './ThemeToggle'

afterEach(() => {
  document.documentElement.classList.remove('theme-control')
})

describe('ThemeToggle', () => {
  it('tema Control (escuro) e o default: aplica a classe theme-control ao montar', () => {
    render(<ThemeToggle />)
    expect(document.documentElement.classList.contains('theme-control')).toBe(true)
  })

  it('clicar alterna para Document (claro): remove a classe', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button'))
    expect(document.documentElement.classList.contains('theme-control')).toBe(false)
  })

  it('alvo de toque tem no minimo 44px (min-h-11)', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button').className).toContain('min-h-11')
  })

  it('prefers-reduced-motion: nao aplica a animacao icon-swap no span do icone', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    render(<ThemeToggle />)
    const svg = screen.getByRole('button').querySelector('svg')
    const icone = svg?.closest('span')
    expect(icone).not.toBeNull()
    expect((icone as HTMLSpanElement).style.animation).toBe('')
    vi.unstubAllGlobals()
  })
})
