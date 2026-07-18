import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { LiveClock } from './LiveClock'

afterEach(() => vi.useRealTimers())

describe('LiveClock', () => {
  it('mostra a hora atual no formato HH:MM:SS', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T15:19:00Z'))
    render(<LiveClock />)
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })
})
