import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }) }))

import App from './App'
import { AuthProvider } from './lib/useAuth'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function seedValidToken() {
  const token = `${b64url({ alg: 'HS256' })}.${b64url({ exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`
  localStorage.setItem('sentinela_token', token)
}

function wrap(node: ReactNode, initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider>{node}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => seedValidToken())
afterEach(() => localStorage.clear())

describe('App routing', () => {
  // Marcador de "DashboardPage montou": 'Áreas monitoradas' e texto estatico da
  // pagina (sem depender de dados), substitui o antigo 'Detalhe do sensor' — o
  // SensorDetailPanel foi removido do fluxo principal na Task 14.
  it('"/" renderiza a DashboardPage', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Áreas monitoradas')).toBeInTheDocument())
  })

  it('"/sensor/:code" redireciona para "/?sensor=:code" e renderiza a DashboardPage', async () => {
    // O redirect App-level ainda existe; a DashboardPage nao consome mais o
    // ?sensor (detalhe dropado), entao afirmamos apenas que a rota resolve na
    // DashboardPage sem 404/crash.
    render(wrap(<App />, '/sensor/TEMP-EXP-01'))
    await waitFor(() => expect(screen.getByText('Áreas monitoradas')).toBeInTheDocument())
  })

  it('"/area/:areaCode" redireciona para "/?area=:areaCode"', async () => {
    render(wrap(<App />, '/area/EXPURGO'))
    // 'Áreas monitoradas' e estatico (aparece na hora); o card da area so
    // aparece apos a query de sensores resolver -- por isso esperamos o testid.
    await waitFor(() => expect(screen.getByTestId('area-card-EXPURGO')).toBeInTheDocument())
  })

  it('fluxo completo de auth: sem login redireciona, loga, navega, desloga, bloqueia de novo', async () => {
    localStorage.clear() // sobrescreve o beforeEach (que semeia token valido) -- comeca deslogado de proposito
    render(wrap(<App />, '/'))

    // sem token, tentar acessar / redireciona pra tela de login
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))

    // login ok, entra na DashboardPage
    await waitFor(() => expect(screen.getByText('Áreas monitoradas')).toBeInTheDocument(), { timeout: 3000 })

    // desloga
    await userEvent.click(screen.getByRole('button', { name: /sair/i }))

    // volta pra tela de login, e o token sumiu do storage
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })
})
