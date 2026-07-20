import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WidgetPalette } from './WidgetPalette'

describe('WidgetPalette', () => {
  it('emite o tipo ao iniciar o arraste', () => {
    const onDragStartType = vi.fn()
    render(<WidgetPalette onAdd={vi.fn()} onDragStartType={onDragStartType} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Adicionar' }))
    const item = screen.getByText(/Card de área/)
    fireEvent.dragStart(item, { dataTransfer: { setData: vi.fn() } })
    expect(onDragStartType).toHaveBeenCalledWith('area')
  })
})
