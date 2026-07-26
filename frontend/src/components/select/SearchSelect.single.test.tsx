import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchSelect } from './SearchSelect'
import { sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const mk = (code: string, name: string): SensorMeta => ({
  sensor_code: code, name, unidade: '°C', protocolo_origem: '4-20ma',
  measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: 'A1', name: 'Expurgo', category: 'c' },
})
const items = [mk('S1', 'Autoclave 1'), mk('S2', 'Camara Fria'), mk('S3', 'Lavadora')]

describe('SearchSelect single', () => {
  it('mostra o label do item selecionado', () => {
    render(<SearchSelect items={items} config={sensorConfig} value="S2" onChange={vi.fn()} label="Sensor" />)
    expect(screen.getByDisplayValue('Camara Fria')).toBeInTheDocument()
  })

  it('digitar filtra as opções pelo nome', async () => {
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('combobox'))
    // substring (não word-start): "mara" casa no meio de "Camara Fria" e não
    // aparece em "Autoclave 1"/"Lavadora"
    await userEvent.type(screen.getByRole('combobox'), 'mara')
    expect(screen.getByText('Camara Fria')).toBeInTheDocument()
    expect(screen.queryByText('Autoclave 1')).toBeNull()
    expect(screen.queryByText('Lavadora')).toBeNull()
  })

  it('o combobox tem nome acessível vindo do label', () => {
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={vi.fn()} label="Sensor" />)
    expect(screen.getByRole('combobox', { name: 'Sensor' })).toBeInTheDocument()
  })

  it('escolher uma opção chama onChange com o id', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByText('Autoclave 1'))
    expect(onChange).toHaveBeenCalledWith('S1')
  })

  it('limpar (×) chama onChange(null)', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value="S1" onChange={onChange} />)
    await userEvent.click(screen.getByLabelText('Limpar seleção'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('id sem item correspondente cai no próprio id como fallback (sem crash)', () => {
    render(<SearchSelect items={items} config={sensorConfig} value="SX" onChange={vi.fn()} />)
    expect(screen.getByDisplayValue('SX')).toBeInTheDocument()
  })

  it('abre a modal Pesquisar mais e selecionar lá chama onChange', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('button', { name: /Pesquisar mais/ }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Camara Fria'))
    expect(onChange).toHaveBeenCalledWith('S2')
  })
})
