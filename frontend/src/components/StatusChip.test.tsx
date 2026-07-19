import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusChip } from './StatusChip'

describe('StatusChip', () => {
  it('mostra o texto do estado (nao so cor)', () => {
    render(<StatusChip state="crit" />)
    expect(screen.getByText('Fora')).toBeInTheDocument()
  })

  it('inclui um icone (svg) ao lado do texto', () => {
    const { container } = render(<StatusChip state="ok" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
