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
  it('"/" renderiza a Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument())
  })

  it('"/sensor/:code" renderiza o Detalhe do sensor certo', async () => {
    render(wrap(<App />, '/sensor/TEMP-EXP-01'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())
  })

  it('fluxo completo: Overview -> Area -> Sensor -> Voltar -> Overview', async () => {
    render(wrap(<App />, '/'))
    await waitFor(() => expect(screen.getByText('Expurgo')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByTestId('area-card-EXPURGO'))
    await waitFor(() => expect(screen.getByText('Pressão diferencial')).toBeInTheDocument(), { timeout: 3000 })

    await userEvent.click(screen.getByText('Temperatura'))
    await waitFor(() => expect(screen.getByText(/Temperatura — Expurgo/)).toBeInTheDocument())

    await userEvent.click(screen.getByRole('link', { name: /voltar/i }))
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument(), { timeout: 3000 })
  })

  it('fluxo completo de auth: sem login redireciona, loga, navega, desloga, bloqueia de novo', async () => {
    localStorage.clear() // sobrescreve o beforeEach (que semeia token valido) -- comeca deslogado de proposito
    render(wrap(<App />, '/'))

    // sem token, tentar acessar / redireciona pra tela de login
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))

    // login ok, entra na Overview
    await waitFor(() => expect(screen.getByText('Visão geral')).toBeInTheDocument(), { timeout: 3000 })

    // desloga
    await userEvent.click(screen.getByRole('button', { name: /sair/i }))

    // volta pra tela de login, e o token sumiu do storage
    await waitFor(() => expect(screen.getByLabelText('Usuário')).toBeInTheDocument())
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })
})
