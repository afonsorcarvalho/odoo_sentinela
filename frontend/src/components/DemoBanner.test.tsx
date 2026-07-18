import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { DemoBanner } from './DemoBanner'

describe('DemoBanner', () => {
  it('mostra o banner e o botao de simular; clicar chama onSimulate', () => {
    const onSimulate = vi.fn()
    render(<DemoBanner simulating={false} onSimulate={onSimulate} onReset={vi.fn()} />)
    expect(screen.getByText(/Ambiente de demonstração/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Simular não conformidade/ }))
    expect(onSimulate).toHaveBeenCalled()
  })

  it('simulating=true troca o botao para "Interromper simulação"', () => {
    render(<DemoBanner simulating onSimulate={vi.fn()} onReset={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Interromper simulação' })).toBeInTheDocument()
  })
})
