import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import App from './App'

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('App routing', () => {
  it('"/" renderiza a Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })

  it('"/sensor/:code" renderiza o Detalhe do sensor certo', async () => {
    render(wrap(<App />, '/sensor/TEMP-EXP-01'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
  })

  it('clicar num cartao da Overview navega pro Detalhe, e Voltar retorna', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByTestId('area-card-EXPURGO'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })
})
