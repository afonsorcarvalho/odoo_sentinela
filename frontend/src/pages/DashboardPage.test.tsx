import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'

// ECharts mockado (sem canvas em jsdom) — DashboardPage renderiza SensorDetailPanel -> TimeSeriesChart.
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import { DashboardPage } from './DashboardPage'
import { AuthProvider } from '../lib/useAuth'

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

describe('DashboardPage', () => {
  it('sem querystring, mostra os cards de area e o painel de detalhe do 1o sensor', async () => {
    renderWithProviders(['/'])
    await waitFor(() => expect(screen.getByText('Detalhe do sensor')).toBeInTheDocument())
    expect(screen.getAllByTestId(/area-card-/).length).toBeGreaterThan(0)
  })

  it('com ?sensor=CODE, o painel de detalhe abre nesse sensor', async () => {
    renderWithProviders(['/?sensor=TEMP-PRE-01'])
    // Nome da area + measurement_type.name no fixture mock (TEMP-PRE-01) e
    // "Preparo/Esterilização" / "Temperatura" — ver frontend/src/lib/api/mock/fixtures.ts.
    await waitFor(() => expect(screen.getByText('Preparo/Esterilização · Temperatura')).toBeInTheDocument())
  })

  it('mostra o painel de alarmes e o topbar', async () => {
    renderWithProviders(['/'])
    await waitFor(() => expect(screen.getByText('Alarmes')).toBeInTheDocument())
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
  })

  it('ao clicar num sensor de outra area no AreaCard, o painel de detalhe passa a mostrar esse sensor', async () => {
    renderWithProviders(['/'])
    // Sem querystring, o painel de detalhe abre no 1o sensor do 1o grupo
    // (Expurgo · Temperatura, ver fixtures.ts / App.test.tsx).
    await waitFor(() => expect(screen.getByText('Expurgo · Temperatura')).toBeInTheDocument())

    // Clica no 1o sensor (Temperatura / TEMP-PRE-01) do card de uma area
    // diferente (Preparo/Esterilização) -- exercita selectSensor ->
    // setSearchParams -> re-render do SensorDetailPanel.
    const preparoCard = screen.getByTestId('area-card-PREPARO_ESTER')
    const [temperaturaButton] = within(preparoCard).getAllByRole('button')
    await userEvent.click(temperaturaButton)

    await waitFor(() => expect(screen.getByText('Preparo/Esterilização · Temperatura')).toBeInTheDocument())
    expect(screen.queryByText('Expurgo · Temperatura')).not.toBeInTheDocument()
  })
})
