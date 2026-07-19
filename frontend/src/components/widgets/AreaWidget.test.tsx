import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AreaWidget } from './AreaWidget'

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('AreaWidget', () => {
  it('renderiza o AreaCard da área existente no mock', async () => {
    // EXPURGO existe no mock (SENSOR e SENSOR_PRESSAO_EXP, ver fixtures.ts).
    renderWithClient(<AreaWidget areaCode="EXPURGO" />)
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
  })

  it('mostra placeholder quando área não existe', async () => {
    renderWithClient(<AreaWidget areaCode="__NAO_EXISTE__" />)
    await waitFor(() => expect(screen.getByText(/configurar|indisponível|sem dados/i)).toBeInTheDocument())
  })
})
