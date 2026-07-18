import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { LoginPage } from './LoginPage'

function wrap() {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>pagina protegida</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('LoginPage', () => {
  it('credencial certa navega pra /', async () => {
    localStorage.clear()
    render(wrap())
    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))
    await waitFor(() => expect(screen.getByText('pagina protegida')).toBeInTheDocument())
  })

  it('credencial errada mostra erro, nao navega', async () => {
    localStorage.clear()
    render(wrap())
    await userEvent.type(screen.getByLabelText('Usuário'), 'admin')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: /entrar/i }))
    await waitFor(() => expect(screen.getByText(/usuário ou senha inválidos/i)).toBeInTheDocument())
    expect(screen.queryByText('pagina protegida')).not.toBeInTheDocument()
  })
})
