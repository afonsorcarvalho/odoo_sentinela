import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

// Seletor de sensores substituido por botoes simples (a UI real e testada em select/).
vi.mock('../components/select/SensorSelect', () => ({
  SensorSelect: ({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) => (
    <div>
      <span data-testid="sel">{value.length}</span>
      <button type="button" onClick={() => onChange(['TEMP-EXP-01'])}>um sensor</button>
      <button type="button" onClick={() => onChange(Array.from({ length: 20 }, (_, i) => `S${i}`))}>vinte</button>
      <button type="button" onClick={() => onChange(Array.from({ length: 21 }, (_, i) => `S${i}`))}>vinte e um</button>
    </div>
  ),
}))

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
  await userEvent.click(screen.getByRole('button', { name: 'um sensor' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gerar' }))
}

const origCreate = URL.createObjectURL
const origRevoke = URL.revokeObjectURL

describe('RelatoriosPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  })

  it('não pré-seleciona sensores: Gerar desabilitado até escolher', async () => {
    renderPage()
    expect(screen.getByTestId('sel')).toHaveTextContent('0')
    expect(screen.getByRole('button', { name: 'Gerar' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'um sensor' }))
    expect(screen.getByRole('button', { name: 'Gerar' })).toBeEnabled()
  })

  it('mais de 20 sensores: Gerar desabilitado com mensagem; 20 é permitido', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'vinte' }))
    expect(screen.getByRole('button', { name: 'Gerar' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'vinte e um' }))
    expect(screen.getByRole('button', { name: 'Gerar' })).toBeDisabled()
    expect(screen.getByText(/Máximo de 20 sensores por relatório/)).toBeInTheDocument()
  })

  it('Imprimir abre a janela sincronamente e depois aponta para o blob', async () => {
    const janela = { location: { href: '' }, close: vi.fn() } as unknown as Window
    const open = vi.spyOn(window, 'open').mockReturnValue(janela)
    URL.createObjectURL = vi.fn(() => 'blob:pdf')
    URL.revokeObjectURL = vi.fn()
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    await userEvent.click(screen.getByRole('button', { name: 'Imprimir' }))
    expect(open).toHaveBeenCalledWith('', '_blank')
    await waitFor(() => expect(janela.location.href).toBe('blob:pdf'))
  })

  it('Imprimir com popup bloqueado mostra erro e não busca o PDF', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    const spy = vi.spyOn(reportApi, 'getReportPdf')
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    await userEvent.click(screen.getByRole('button', { name: 'Imprimir' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/janela de impressão/)
    expect(spy).not.toHaveBeenCalled()
  })

  it('erro de PDF antigo some ao gerar novo relatório', async () => {
    vi.spyOn(reportApi, 'getReportPdf').mockRejectedValue(new Error('falha pdf'))
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    await userEvent.click(screen.getByRole('button', { name: 'Baixar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('falha pdf')
    await userEvent.click(screen.getByRole('button', { name: 'Gerar' }))
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    expect(screen.queryByText('falha pdf')).not.toBeInTheDocument()
  })

  it('mês parcial: notas sob a tabela só quando parcial', async () => {
    renderPage()
    await gerar('2026-01-15', '2026-06-10')
    const sec = await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    expect(within(sec).getByText('Primeiro mês parcial: dados de 15/01/2026 a 31/01/2026.')).toBeInTheDocument()
    expect(within(sec).getByText('Último mês parcial: dados de 01/06/2026 a 10/06/2026.')).toBeInTheDocument()
  })

  it('mês completo: sem nota de mês parcial', async () => {
    renderPage()
    await gerar('2026-01-01', '2026-06-30')
    await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    expect(screen.queryByText(/mês parcial/i)).not.toBeInTheDocument()
  })

  it('alteração de limite posterior ao fim do período é marcada', async () => {
    const real = await reportApi.getReport({ sensores: ['TEMP-EXP-01'], inicio: '2026-01-10', fim: '2026-01-10' })
    real.sensores[0].alteracoes_limite = [{ quando: '2026-01-12T15:00:00+00:00', campo: 'limite_max', de: 7, para: 8 }]
    vi.spyOn(reportApi, 'getReport').mockResolvedValue(real)
    renderPage()
    await gerar('2026-01-10', '2026-01-10')
    const sec = await screen.findByRole('region', { name: /TEMP-EXP-01/ })
    expect(within(sec).getByText(/Limite alterado em 12\/01\/2026 12:00.*após o período/)).toBeInTheDocument()
  })

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

describe('numFormatter', () => {
  it('aplica casas, zero-pad e vírgula como o PDF', async () => {
    const { numFormatter } = await import('./RelatoriosPage')
    const f = numFormatter({ casas_decimais: 1, digitos_inteiros: 3 })
    expect(f(9.5)).toBe('009,5')
    expect(f(-2.26)).toBe('-002,3')
    expect(f(null)).toBe('—')
    expect(numFormatter({ casas_decimais: 2, digitos_inteiros: 1 })(-0.001)).toBe('0,00')
  })
})
