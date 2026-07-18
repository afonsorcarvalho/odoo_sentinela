import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router'
import { AuthProvider } from '../lib/useAuth'
import { Topbar } from './Topbar'

function wrap(node: React.ReactNode) {
  return (
    <MemoryRouter>
      <AuthProvider>{node}</AuthProvider>
    </MemoryRouter>
  )
}

describe('Topbar', () => {
  it('mostra a marca, o nome da unidade e o indicador AO VIVO', () => {
    render(wrap(<Topbar healthy unitName="Hospital Demonstração" />))
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
    expect(screen.getByText('CME')).toBeInTheDocument()
    expect(screen.getByText('Hospital Demonstração')).toBeInTheDocument()
    expect(screen.getByText('AO VIVO')).toBeInTheDocument()
  })

  it('healthy=true mostra "Registro íntegro"; healthy=false nao mostra', () => {
    const { rerender } = render(wrap(<Topbar healthy unitName="X" />))
    expect(screen.getByText('Registro íntegro')).toBeInTheDocument()

    rerender(wrap(<Topbar healthy={false} unitName="X" />))
    expect(screen.queryByText('Registro íntegro')).not.toBeInTheDocument()
  })

  it('header permite quebra de linha em telas estreitas (flex-wrap)', () => {
    render(wrap(<Topbar healthy unitName="X" />))
    expect(screen.getByText('Sentinela').closest('header')).toHaveClass('flex-wrap')
  })
})
