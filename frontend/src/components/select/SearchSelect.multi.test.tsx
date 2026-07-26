import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchSelect } from './SearchSelect'
import { areaConfig, type Area } from './entityConfigs'

const areas: Area[] = [
  { area_code: 'A1', name: 'Expurgo', category: 'c' },
  { area_code: 'A2', name: 'Preparo', category: 'c' },
  { area_code: 'A3', name: 'Arsenal', category: 'c' },
]

describe('SearchSelect multi', () => {
  it('mostra chips dos selecionados', () => {
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1', 'A3']} onChange={vi.fn()} />)
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Arsenal')).toBeInTheDocument()
  })

  it('escolher no dropdown adiciona o id via onChange', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByText('Preparo'))
    expect(onChange).toHaveBeenCalledWith(['A1', 'A2'])
  })

  it('remover chip chama onChange sem o id', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1', 'A3']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Remover Expurgo' }))
    expect(onChange).toHaveBeenCalledWith(['A3'])
  })

  it('Pesquisar mais em multi confirma o conjunto marcado', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('button', { name: /Pesquisar mais/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Arsenal' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(onChange).toHaveBeenCalledWith(['A1', 'A3'])
  })
})
