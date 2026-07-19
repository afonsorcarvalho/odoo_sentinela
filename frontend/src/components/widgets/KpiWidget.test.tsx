import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KpiWidget } from './KpiWidget'

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('KpiWidget', () => {
  it('renderiza o label quando fornecido', () => {
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" label="Pressão Expurgo" />)
    expect(screen.getByText('Pressão Expurgo')).toBeInTheDocument()
  })
  it('mostra o sensorCode como fallback de título quando sem label', () => {
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" />)
    expect(screen.getByText(/PRESS-EXP-01/)).toBeInTheDocument()
  })
})
