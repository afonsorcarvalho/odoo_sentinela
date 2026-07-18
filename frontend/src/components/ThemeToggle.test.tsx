import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, afterEach } from 'vitest'
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
})
