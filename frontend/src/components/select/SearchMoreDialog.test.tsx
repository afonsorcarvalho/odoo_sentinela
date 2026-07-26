import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchMoreDialog } from './SearchMoreDialog'
import { sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const mk = (code: string, name: string, area: string): SensorMeta => ({
  sensor_code: code, name, unidade: '°C', protocolo_origem: '4-20ma',
  measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: area, name: area, category: 'c' },
})
const items = [mk('S1', 'Autoclave 1', 'Expurgo'), mk('S2', 'Camara Fria', 'Arsenal')]

describe('SearchMoreDialog', () => {
  it('renderiza tabela com as colunas do config (role=dialog)', () => {
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Autoclave 1')).toBeInTheDocument()
    // header de coluna
    expect(screen.getByRole('columnheader', { name: 'Área' })).toBeInTheDocument()
  })

  it('busca casa em campo secundário (área), não só no nome', async () => {
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'arsenal' } })
    expect(screen.queryByText('Autoclave 1')).toBeNull()
    expect(screen.getByText('Camara Fria')).toBeInTheDocument()
  })

  it('single: clicar na linha chama onConfirm([id]) e onClose', async () => {
    const onConfirm = vi.fn(); const onClose = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={onConfirm} onClose={onClose} />)
    await userEvent.click(screen.getByText('Camara Fria'))
    expect(onConfirm).toHaveBeenCalledWith(['S2'])
    expect(onClose).toHaveBeenCalled()
  })

  it('multi: marca checkboxes e Confirmar chama onConfirm com o conjunto', async () => {
    const onConfirm = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple initialSelectedIds={['S1']} onConfirm={onConfirm} onClose={vi.fn()} />)
    // S1 já marcado; marca S2
    await userEvent.click(screen.getByRole('checkbox', { name: /Camara Fria/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(onConfirm).toHaveBeenCalledWith(['S1', 'S2'])
  })

  it('Esc fecha só a modal (onClose)', async () => {
    const onClose = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
