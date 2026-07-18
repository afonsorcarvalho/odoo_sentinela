import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, within, act } from '@testing-library/react'
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
    // Timeout maior que o default (1000ms): `ready` agora exige o 1o ponto ao
    // vivo de cada sensor (liveApi mock, timer real aqui, so emite apos
    // TICK_MS=1000ms) — ver OverviewPage.tsx.
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })
    expect(screen.getByText('Preparo/Esterilização')).toBeInTheDocument()
    expect(screen.getByText('Arsenal')).toBeInTheDocument()
  })

  it('Arsenal mostra "Sem limite" (sem threshold configurado)', async () => {
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText('Arsenal')).toBeInTheDocument(), { timeout: 3000 })
    // Ha 1 card por area; o texto "Sem limite" so deve aparecer pro Arsenal.
    // `ready` (OverviewPage.tsx) so libera os cards apos o 1o ponto ao vivo de
    // TODOS os sensores (liveApi mock, timer real aqui, so emite apos
    // TICK_MS=1000ms) — ate la a pagina mostra skeletons, entao "Sem limite"
    // so aparece, e ja de forma correta e exclusiva pro Arsenal (sem
    // threshold), depois que os cards de fato renderizam.
    await waitFor(() => expect(screen.getAllByText('Sem limite')).toHaveLength(1), { timeout: 3000 })
  })

  it('nao mostra "Sem limite" prematuramente para sensor com threshold (aguarda 1o tick ao vivo)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(wrap(<OverviewPage />))
    // sensores/thresholds resolvem quase instantaneamente (mock), mas o 1o
    // ponto ao vivo so chega em ~1000ms (TICK_MS do liveApi) — antes disso,
    // a pagina nao deve renderizar nenhum card ainda (seria "Sem limite"
    // enganoso pro Expurgo, que TEM threshold).
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })
    expect(screen.queryByText('Expurgo')).not.toBeInTheDocument()

    // apos o 1o tick, os cards aparecem com o estado real (nao "Sem limite"
    // para quem tem threshold).
    await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument())
    const expurgoCard = screen.getByTestId('area-card-EXPURGO')
    expect(within(expurgoCard).queryByText('Sem limite')).not.toBeInTheDocument()

    vi.useRealTimers()
  })

  it('erro ao listar sensores mostra retry, que refaz a chamada', async () => {
    const spy = vi.spyOn(api.metaApi, 'listSensors').mockRejectedValueOnce(new Error('falhou'))
    render(wrap(<OverviewPage />))
    await waitFor(() => expect(screen.getByText(/falha/i)).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /tentar de novo/i }))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })
    spy.mockRestore()
  })
})
