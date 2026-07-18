import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WindowSelector } from './WindowSelector'
import { ThresholdBadge } from './ThresholdBadge'
import type { Threshold } from '../lib/types'

const t: Threshold = { sensor_id: 'S', limite_min: 18, limite_max: 22, is_valor_padrao_regulatorio: true }

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

describe('ThresholdBadge', () => {
  it('mostra min/max e marca padrao regulatorio', () => {
    render(<ThresholdBadge threshold={t} unidade="C" />)
    expect(screen.getByText(/18/)).toBeInTheDocument()
    expect(screen.getByText(/22/)).toBeInTheDocument()
    expect(screen.getByText(/RDC 15|regulat/i)).toBeInTheDocument()
  })
  it('sem threshold mostra "sem limite"', () => {
    render(<ThresholdBadge threshold={null} unidade="C" />)
    expect(screen.getByText(/sem limite/i)).toBeInTheDocument()
  })
})
