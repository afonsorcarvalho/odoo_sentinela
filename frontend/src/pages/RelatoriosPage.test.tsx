import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { RelatoriosPage } from './RelatoriosPage'
import { AuthProvider } from '../lib/useAuth'
import { reportApi } from '../lib/api'

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthProvider>
          <RelatoriosPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function gerar(inicio: string, fim: string) {
  fireEvent.change(screen.getByLabelText('Data início'), { target: { value: inicio } })
  fireEvent.change(screen.getByLabelText('Data fim'), { target: { value: fim } })
  // espera os sensores carregarem (seleção default = todos)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Gerar' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: 'Gerar' }))
}

describe('RelatoriosPage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('gera relatório de um dia: 24 linhas, marcador fora do limite e aviso de limite', async () => {
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    const sec = await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    const rows = within(within(sec).getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(25) // cabeçalho + 24
    expect(within(sec).getAllByLabelText('fora do limite').length).toBeGreaterThan(0)
    expect(within(sec).getByText(/Limite alterado em/)).toBeInTheDocument()
    expect(within(sec).getByText('Sem dados')).toBeInTheDocument()
    expect(within(sec).getByText('Falha de instrumento')).toBeInTheDocument()
  })

  it('Baixar PDF chama getReportPdf com os params atuais', async () => {
    const spy = vi.spyOn(reportApi, 'getReportPdf')
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    renderPage()
    await gerar('2026-01-10', '2026-01-12')
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    await userEvent.click(screen.getByRole('button', { name: 'Baixar PDF' }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    const p = spy.mock.calls[0][0]
    expect(p.inicio).toBe('2026-01-10')
    expect(p.fim).toBe('2026-01-12')
    expect(p.sensores).toContain('TEMP-EXP-01')
  })

  it('mostra mensagem de erro da API', async () => {
    vi.spyOn(reportApi, 'getReport').mockRejectedValue(new Error('Período máximo é 366 dias'))
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    expect(await screen.findByRole('alert')).toHaveTextContent('Período máximo é 366 dias')
  })
})
