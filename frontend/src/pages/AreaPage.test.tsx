import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router'
import type { ReactNode } from 'react'

import { AreaPage } from './AreaPage'

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/area/:areaCode" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AreaPage', () => {
  it('lista os 2 sensores do Expurgo (temperatura + pressao)', async () => {
    render(wrap(<AreaPage />, '/area/EXPURGO'))
    await waitFor(() => expect(screen.getByText('Temperatura')).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByText('Pressão diferencial')).toBeInTheDocument()
  })

  it('area inexistente mostra mensagem, nao quebra', async () => {
    render(wrap(<AreaPage />, '/area/NAO-EXISTE'))
    await waitFor(() => expect(screen.getByText(/não encontrada/i)).toBeInTheDocument(), { timeout: 3000 })
  })

  it('Arsenal (1 sensor, sem threshold) mostra Sem limite', async () => {
    render(wrap(<AreaPage />, '/area/ARSENAL'))
    await waitFor(() => expect(screen.getByText('Sem limite')).toBeInTheDocument(), { timeout: 3000 })
  })
})
