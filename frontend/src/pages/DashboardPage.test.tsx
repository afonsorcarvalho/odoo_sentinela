import { render, screen, waitFor, within, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

// ECharts mockado (sem canvas em jsdom). O registry de widgets importa
// estaticamente o TimeseriesWidget (-> echarts) mesmo sem widget timeseries no
// default layout, entao o mock continua necessario apos remover o
// SensorDetailPanel.
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { DashboardPage } from './DashboardPage'
import { AuthProvider, TOKEN_STORAGE_KEY } from '../lib/useAuth'

// AuthProvider necessario: Topbar -> LogoutButton usa useAuth(), que lanca
// erro fora de um AuthProvider (o brief original nao incluia este wrapper).
function renderWithProviders(initialEntries: string[]) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// Injeta um token JWT (sem verificacao de assinatura no client) com is_admin.
// exp em segundos (decodeJwtExp faz *1000). Chamar ANTES do render: o
// AuthProvider le o token no initializer do useState em tempo de montagem.
function setAdminToken() {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + 3600
  localStorage.setItem(TOKEN_STORAGE_KEY, `${b64({ alg: 'HS256' })}.${b64({ is_admin: true, exp })}.sig`)
}

describe('DashboardPage', () => {
  afterEach(() => {
    vi.useRealTimers()
    // Isola os testes de gate: sem isso o token admin vazaria para o teste
    // de nao-admin (ou para qualquer teste seguinte) conforme a ordem.
    localStorage.clear()
  })

  it('carousel_interval_ms do mock (configApi, 4000) flui ate o AreaCard: nao avanca em 3000ms, avanca em 4000ms', async () => {
    // Valor do mock (frontend/src/lib/api/mock/configApi.ts) e deliberadamente
    // 4000, diferente do fallback hardcoded 3000 usado no AreaWidget
    // (config.data?.carousel_interval_ms ?? 3000) e do default do AreaCard.
    // O AreaCard agora renderiza via AreaWidget dentro do DashboardGrid; o
    // carrossel (setInterval no AreaCard) continua alimentado pelo mesmo mock.
    // Fake timers desde o inicio (mesmo padrao de AreaCard.test.tsx) +
    // vi.advanceTimersByTimeAsync para deixar as queries do mock (promises
    // simples, sem setTimeout) resolverem antes de avancar o relogio.
    vi.useFakeTimers()
    renderWithProviders(['/'])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // EXPURGO e o 1o grupo do fixture, com 2 sensores (TEMP-EXP-01,
    // PRESS-EXP-01) -- ativa o carrossel automatico do AreaCard.
    const expurgoCard = screen.getByTestId('area-card-EXPURGO')
    expect(within(expurgoCard).getByText('Temperatura')).toBeInTheDocument()

    // A 1ms de completar 4000ms (o valor real do mock) o carrossel AINDA NAO
    // avancou -- em particular, ja passou dos 3000ms do fallback hardcoded
    // (coincidentemente igual ao antigo valor do mock): se o wiring tivesse
    // caido de volta pro fallback, o carrossel ja teria avancado aqui.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3999)
    })
    expect(within(expurgoCard).getByText('Temperatura')).toBeInTheDocument()

    // No ms exato de 4000ms, o carrossel avanca.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(within(expurgoCard).getByText('Pressão diferencial')).toBeInTheDocument()
    expect(within(expurgoCard).queryByText('Temperatura')).not.toBeInTheDocument()
  })

  it('mostra o painel de alarmes e o topbar', async () => {
    renderWithProviders(['/'])
    // 'Alarmes' vem do AlarmsWidget (default layout) e 'Sentinela' do Topbar.
    await waitFor(() => expect(screen.getByText('Alarmes')).toBeInTheDocument())
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
  })

  it('nao mostra botao Editar para nao-admin', async () => {
    renderWithProviders(['/'])
    // Espera o grid montar (AlarmsWidget rende 'Alarmes') antes de afirmar
    // ausencia, pra nao passar so por ainda nao ter renderizado nada.
    await waitFor(() => expect(screen.getByText('Alarmes')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /editar/i })).toBeNull()
  })

  it('mostra botao Editar para admin', async () => {
    setAdminToken()
    renderWithProviders(['/'])
    expect(await screen.findByRole('button', { name: /editar/i })).toBeInTheDocument()
  })

  it('admin: clicar em Editar monta o DashboardEditor (palette + Salvar/Cancelar) e esconde Editar', async () => {
    // Cobre o caminho Editar -> DashboardEditor (que jsdom consegue montar; o
    // layout visivel do react-grid-layout depende de medicao de largura via
    // WidthProvider, que e 0 no jsdom -- essa parte fica fora deste teste).
    setAdminToken()
    renderWithProviders(['/'])
    await userEvent.click(await screen.findByRole('button', { name: /editar/i }))

    expect(await screen.findByRole('button', { name: /adicionar/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar/i })).toBeNull()
  })
})
