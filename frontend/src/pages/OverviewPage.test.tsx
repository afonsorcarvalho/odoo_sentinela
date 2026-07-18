import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { OverviewPage } from './OverviewPage'
import * as api from '../lib/api'

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

describe('OverviewPage', () => {
  it('renderiza as 3 areas apos carregar', async () => {
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
    expect(screen.getByText('Preparo/Esterilização')).toBeInTheDocument()
    expect(screen.getByText('Arsenal')).toBeInTheDocument()
  })

  it('Arsenal mostra "Sem limite" (sem threshold configurado)', async () => {
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText('Arsenal')).toBeInTheDocument())
    // Ha 1 card por area; o texto "Sem limite" so deve aparecer pro Arsenal.
    // Timeout maior que o default (1000ms): o liveApi mock (timer real, sem
    // fake timers aqui) so emite o 1o ponto apos TICK_MS=1000ms — Expurgo e
    // Preparo tambem mostram "Sem limite" ate la (sem `live` ainda), entao o
    // texto so fica exclusivo do Arsenal depois do 1o tick.
    await waitFor(() => expect(screen.getAllByText('Sem limite')).toHaveLength(1), { timeout: 3000 })
  })

  it('erro ao listar sensores mostra retry, que refaz a chamada', async () => {
    const spy = vi.spyOn(api.metaApi, 'listSensors').mockRejectedValueOnce(new Error('falhou'))
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText(/falha/i)).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /tentar de novo/i }))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
    spy.mockRestore()
  })
})
