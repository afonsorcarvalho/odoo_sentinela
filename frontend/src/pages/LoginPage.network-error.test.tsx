import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router'

vi.mock('../lib/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isAdmin: false,
    login: vi.fn().mockRejectedValue(new Error('erro de rede')),
    logout: vi.fn(),
  }),
}))

import { LoginPage } from './LoginPage'

describe('LoginPage (erro de rede)', () => {
  it('login falhando por erro de rede mostra mensagem distinta de credencial invalida', async () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>pagina protegida</div>} />
        </Routes>
      </MemoryRouter>,
    )
    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))
    await waitFor(() =>
      expect(screen.getByText(/não foi possível conectar ao servidor/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText('pagina protegida')).not.toBeInTheDocument()
    expect(screen.queryByText(/usuário ou senha inválidos/i)).not.toBeInTheDocument()
  })
})
