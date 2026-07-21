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
import { configApi } from '../lib/api'

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
    // Empurrão vertical (push): o sensor que sai coexiste com o que entra
    // durante carousel_transition_ms (mock = 500ms). Após a transição, o
    // readout antigo é removido.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
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

  it('config com erro: mostra erro/retry e NÃO cai no layout default (nem Editar)', async () => {
    // Regressão da "perda de layout no upgrade": quando o /config falha
    // (ex.: backend reiniciando logo após um upgrade de módulo), o frontend
    // NÃO pode renderizar o layout default — que, se salvo, sobrescreveria o
    // layout real (íntegro no DB, só não-carregado). Deve mostrar erro+retry.
    setAdminToken()
    const spy = vi.spyOn(configApi, 'getConfig').mockRejectedValue(new Error('backend indisponível'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/']}>
          <AuthProvider>
            <DashboardPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText(/não foi possível carregar/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument()
    // Não renderiza o grid default (sem painel de alarmes do default)...
    expect(screen.queryByText('Alarmes')).toBeNull()
    // ...e não oferece Editar (evita salvar um default sobre o layout real).
    expect(screen.queryByRole('button', { name: /editar/i })).toBeNull()

    spy.mockRestore()
  })

  describe('drill-down (D3)', () => {
    // EXPURGO e o 1o grupo do fixture, com sensor ativo default TEMP-EXP-01
    // ("Temperatura") -- mesma base dos testes de carrossel acima.

    it('clicar no valor do AreaCard (view) abre o SensorDetailDrawer com o sensor certo', async () => {
      renderWithProviders(['/'])
      const expurgoCard = await screen.findByTestId('area-card-EXPURGO')

      // userEvent.click dispara a sequencia real de eventos de ponteiro
      // (pointerdown/mousedown/pointerup/mouseup/click) -- e exatamente essa
      // sequencia que exercitaria uma falsa deteccao de "clique fora"
      // (useDismiss outsidePress escuta pointerdown) SE o drawer ja existisse
      // no DOM no momento do clique. Como o drawer so monta depois que
      // selectedSensorCode vira nao-null (DashboardPage.tsx), o listener de
      // outsidePress do floating-ui (registrado em useEffect apos o mount)
      // nasce depois que este clique ja terminou de se propagar -- por isso
      // basta afirmar que o dialog aparece E continua aberto apos o clique
      // resolver: se houvesse a race, o drawer teria fechado (ou nunca
      // aberto de forma estavel) neste mesmo passo.
      await userEvent.click(within(expurgoCard).getByText('Temperatura'))

      const dialog = await screen.findByRole('dialog')
      expect(within(dialog).getByText('Expurgo · Temperatura')).toBeInTheDocument()
    })

    it('em modo edição (sem provider), clicar no valor do AreaCard NÃO abre o drawer', async () => {
      setAdminToken()
      renderWithProviders(['/'])
      await userEvent.click(await screen.findByRole('button', { name: /editar/i }))
      // Confirma que o DashboardEditor montou (mesmo teste de fumaca do bloco
      // acima) antes de procurar o card dentro dele.
      expect(await screen.findByRole('button', { name: 'Salvar' })).toBeInTheDocument()

      const expurgoCard = await screen.findByTestId('area-card-EXPURGO')
      await userEvent.click(within(expurgoCard).getByText('Temperatura'))

      expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('botão de métrica dentro do painel troca o sensor exibido sem fechar o drawer', async () => {
      renderWithProviders(['/'])
      const expurgoCard = await screen.findByTestId('area-card-EXPURGO')
      await userEvent.click(within(expurgoCard).getByText('Temperatura'))
      const dialog = await screen.findByRole('dialog')
      expect(within(dialog).getByText('Expurgo · Temperatura')).toBeInTheDocument()

      await userEvent.click(within(dialog).getByRole('button', { name: 'Pressão diferencial' }))

      // Mesmo dialog (nao fechou e reabriu) com o outro sensor.
      expect(await screen.findByRole('dialog')).toBe(dialog)
      expect(within(dialog).getByText('Expurgo · Pressão diferencial')).toBeInTheDocument()
    })

    it('fechar pelo botão ✕ seta selectedSensorCode=null (drawer some) e restaura o foco no botão de origem', async () => {
      renderWithProviders(['/'])
      const expurgoCard = await screen.findByTestId('area-card-EXPURGO')
      const valueButton = within(expurgoCard).getByText('Temperatura').closest('button')!
      await userEvent.click(valueButton)
      const dialog = await screen.findByRole('dialog')

      await userEvent.click(within(dialog).getByRole('button', { name: 'Fechar' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
      // FloatingFocusManager (returnFocus, default true) restaura o foco ao
      // activeElement capturado no momento em que o drawer abriu -- que era
      // o botao de valor do AreaCard (foi ele que recebeu o clique).
      await waitFor(() => expect(document.activeElement).toBe(valueButton))
    })
  })
})
