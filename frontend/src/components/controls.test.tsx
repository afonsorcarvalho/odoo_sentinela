import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WindowSelector } from './WindowSelector'

describe('WindowSelector', () => {
  it('marca a janela ativa e emite onChange', async () => {
    const onChange = vi.fn()
    render(<WindowSelector value="24h" onChange={onChange} />)
    const btn = screen.getByRole('button', { name: '24h' })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(onChange).toHaveBeenCalledWith('7d')
  })
})
