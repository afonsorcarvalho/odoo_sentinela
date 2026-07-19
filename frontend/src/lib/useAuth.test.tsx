import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth } from './useAuth'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function Probe() {
  const { isAuthenticated, isAdmin, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="status">{isAuthenticated ? 'dentro' : 'fora'}</span>
      <span data-testid="admin">{isAdmin ? 'sim' : 'nao'}</span>
      <button onClick={() => login('admin', 'admin')}>entrar</button>
      <button onClick={() => logout()}>sair</button>
    </div>
  )
}

beforeEach(() => localStorage.clear())

describe('AuthProvider/useAuth', () => {
  it('comeca deslogado sem token no storage', () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
  })

  it('login com credencial certa guarda token e fica autenticado', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText('entrar'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('dentro'))
    expect(localStorage.getItem('sentinela_token')).not.toBeNull()
  })

  it('logout limpa o token e volta a deslogado', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText('entrar'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('dentro'))
    await userEvent.click(screen.getByText('sair'))
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })

  it('token expirado no storage ja nasce deslogado (e limpa o storage)', () => {
    const expired = `${b64url({ alg: 'HS256' })}.${b64url({ exp: 1_700_000_000 })}.sig` // base fixa, bem no passado
    localStorage.setItem('sentinela_token', expired)
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('fora')
    expect(localStorage.getItem('sentinela_token')).toBeNull()
  })

  it('isAdmin comeca false sem token no storage', () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('admin')).toHaveTextContent('nao')
  })

  it('isAdmin true quando token valido no storage tem is_admin true', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    const token = `${b64url({ alg: 'HS256' })}.${b64url({ is_admin: true, exp })}.sig`
    localStorage.setItem('sentinela_token', token)
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('dentro')
    expect(screen.getByTestId('admin')).toHaveTextContent('sim')
  })

  it('isAdmin false quando token valido no storage tem is_admin false', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    const token = `${b64url({ alg: 'HS256' })}.${b64url({ is_admin: false, exp })}.sig`
    localStorage.setItem('sentinela_token', token)
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(screen.getByTestId('status')).toHaveTextContent('dentro')
    expect(screen.getByTestId('admin')).toHaveTextContent('nao')
  })
})
