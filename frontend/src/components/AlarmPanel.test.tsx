import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AlarmPanel } from './AlarmPanel'
import type { AlarmEvent } from '../lib/types'

const AREA_NAMES = { EXPURGO: 'Expurgo' }

const ABERTO: AlarmEvent = {
  id: 1, sensor_code: 'PRESS-EXP-01', area_code: 'EXPURGO',
  tipo_violacao: 'abaixo_limite', status: 'aberto',
  timestamp_deteccao: 1_753_000_000_000, timestamp_resolucao_sensor: null,
  valor_lido: -1.7, limite_configurado_snapshot: -2.5,
  usuario_responsavel: null, data_resolucao: null, observacoes: null,
}

describe('AlarmPanel', () => {
  it('lista vazia mostra estado "Nenhum alarme ativo"', () => {
    render(<AlarmPanel alarms={[]} areaNameByCode={{}} />)
    expect(screen.getByText('Nenhum alarme ativo.')).toBeInTheDocument()
  })

  it('com alarmes, mostra contador e o tipo em maiusculas', () => {
    render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('NÃO CONFORMIDADE')).toBeInTheDocument()
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
  })
})

function makeAlarm(id: number): AlarmEvent {
  return {
    id, sensor_code: `SNR-${id}`, area_code: 'EXPURGO',
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: 1_753_000_000_000 + id * 60_000, timestamp_resolucao_sensor: null,
    valor_lido: -1.7, limite_configurado_snapshot: -2.5,
    usuario_responsavel: null, data_resolucao: null, observacoes: null,
  }
}

describe('AlarmPanel — limite visivel e "Ver mais"', () => {
  it('com mais alarmes que o limite, renderiza so os N mais recentes e o botao "Ver mais"', () => {
    const alarms = Array.from({ length: 12 }, (_, i) => makeAlarm(i))
    const { container } = render(<AlarmPanel alarms={alarms} areaNameByCode={AREA_NAMES} onVerMais={() => {}} />)
    const items = container.querySelectorAll('ul li')
    expect(items).toHaveLength(8)
    expect(screen.getByRole('button', { name: 'Ver mais (4)' })).toBeInTheDocument()
  })

  it('com alarmes dentro do limite, nao mostra botao "Ver mais"', () => {
    const alarms = Array.from({ length: 5 }, (_, i) => makeAlarm(i))
    render(<AlarmPanel alarms={alarms} areaNameByCode={AREA_NAMES} onVerMais={() => {}} />)
    expect(screen.queryByRole('button', { name: /Ver mais/ })).not.toBeInTheDocument()
  })

  it('clicar em "Ver mais" chama onVerMais', () => {
    const alarms = Array.from({ length: 12 }, (_, i) => makeAlarm(i))
    const onVerMais = vi.fn()
    render(<AlarmPanel alarms={alarms} areaNameByCode={AREA_NAMES} onVerMais={onVerMais} />)
    screen.getByRole('button', { name: 'Ver mais (4)' }).click()
    expect(onVerMais).toHaveBeenCalledTimes(1)
  })
})

describe('AlarmPanel — prop "filtro" (chips de área)', () => {
  it('com filtro, renderiza o conteúdo sob o header e acima da lista', () => {
    render(
      <AlarmPanel
        alarms={[ABERTO]}
        areaNameByCode={AREA_NAMES}
        filtro={<div data-testid="filtro-chips">chips</div>}
      />,
    )
    expect(screen.getByTestId('filtro-chips')).toBeInTheDocument()
  })

  it('sem filtro, o layout permanece inalterado (nada extra renderizado)', () => {
    render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)
    expect(screen.queryByTestId('filtro-chips')).not.toBeInTheDocument()
  })
})

describe('AlarmPanel — prop "mensagemVazio"', () => {
  it('sem mensagemVazio, lista vazia mostra "Nenhum alarme ativo."', () => {
    render(<AlarmPanel alarms={[]} areaNameByCode={{}} />)
    expect(screen.getByText('Nenhum alarme ativo.')).toBeInTheDocument()
  })

  it('com mensagemVazio, lista vazia mostra a mensagem customizada (distinta da default)', () => {
    render(<AlarmPanel alarms={[]} areaNameByCode={{}} mensagemVazio="Nenhuma área selecionada" />)
    expect(screen.getByText('Nenhuma área selecionada')).toBeInTheDocument()
    expect(screen.queryByText('Nenhum alarme ativo.')).not.toBeInTheDocument()
  })
})
