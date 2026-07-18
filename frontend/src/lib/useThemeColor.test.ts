import { describe, it, expect, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useThemeColor } from './useThemeColor'

afterEach(() => {
  document.documentElement.style.removeProperty('--color-crit')
  document.documentElement.classList.remove('dark')
})

describe('useThemeColor', () => {
  it('resolve a custom property oklch para uma cor pintavel em canvas (rgb)', () => {
    document.documentElement.style.setProperty('--color-crit', 'oklch(0.55 0.19 25)')
    const { result } = renderHook(() => useThemeColor('--color-crit'))
    expect(result.current).toMatch(/^rgb\(\d+, \d+, \d+\)$/)
  })

  it('re-resolve quando a classe do <html> muda (troca de tema claro/escuro)', async () => {
    document.documentElement.style.setProperty('--color-crit', 'oklch(0.55 0.19 25)')
    const { result } = renderHook(() => useThemeColor('--color-crit'))
    const light = result.current

    act(() => {
      // Simula o CSS de .dark trocando o token (na app real isso vem do
      // stylesheet; aqui simulamos via inline style, que o MutationObserver
      // de useThemeColor nao diferencia da mudanca real).
      document.documentElement.style.setProperty('--color-crit', 'oklch(0.68 0.20 25)')
      document.documentElement.classList.add('dark')
    })

    await waitFor(() => expect(result.current).not.toBe(light))
  })
})
