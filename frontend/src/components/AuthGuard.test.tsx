import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { AuthGuard } from './AuthGuard'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function wrap(initialPath: string) {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>tela de login</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div>pagina protegida</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('AuthGuard', () => {
  it('sem autenticacao redireciona pra /login', () => {
    localStorage.clear()
    render(wrap('/'))
    expect(screen.getByText('tela de login')).toBeInTheDocument()
    expect(screen.queryByText('pagina protegida')).not.toBeInTheDocument()
  })

  it('com token valido no storage, renderiza a rota protegida', () => {
    const valid = `${b64url({ alg: 'HS256' })}.${b64url({ exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`
    localStorage.setItem('sentinela_token', valid)
    render(wrap('/'))
    expect(screen.getByText('pagina protegida')).toBeInTheDocument()
    localStorage.clear()
  })
})
