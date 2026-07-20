import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AreaWidget } from './AreaWidget'
import { DrillDownContext } from '../../lib/drilldown/DrillDownContext'

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

  it('sem DrillDownContext, clicar no valor do sensor ativo é no-op (nao lanca, nao quebra)', async () => {
    // Gate por ramo (D3): AreaWidget isolado (sem provider, como no ramo de
    // edicao) cai no no-op atual -- so garante ausencia de erro/callback.
    renderWithClient(<AreaWidget areaCode="EXPURGO" />)
    await waitFor(() => expect(screen.getByText('Temperatura')).toBeInTheDocument())
    expect(() => fireEvent.click(screen.getByText('Temperatura'))).not.toThrow()
  })

  it('com DrillDownContext, clicar no valor do sensor ativo chama drill.open com o sensor_code', async () => {
    const open = vi.fn()
    renderWithClient(
      <DrillDownContext.Provider value={{ open }}>
        <AreaWidget areaCode="EXPURGO" />
      </DrillDownContext.Provider>,
    )
    await waitFor(() => expect(screen.getByText('Temperatura')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Temperatura'))
    expect(open).toHaveBeenCalledWith('TEMP-EXP-01')
  })
})
