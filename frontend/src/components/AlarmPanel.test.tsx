import { act, render, screen } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
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

  it('primeiro render nao anima nenhum item, mesmo com alarmes ja presentes', () => {
    render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)
    for (const li of screen.getAllByRole('listitem')) {
      expect(li.className).not.toMatch(/alarm-enter/)
    }
  })

  it('alarme adicionado apos o primeiro render entra com alarm-enter; o preexistente nao', () => {
    const OUTRO: AlarmEvent = { ...ABERTO, id: 2, sensor_code: 'PRESS-EXP-02', timestamp_deteccao: ABERTO.timestamp_deteccao + 60_000 }
    const { rerender } = render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)
    rerender(<AlarmPanel alarms={[OUTRO, ABERTO]} areaNameByCode={AREA_NAMES} />)

    const preexistente = screen.getByText('Expurgo · PRESS-EXP-01').closest('li')!
    const novo = screen.getByText('Expurgo · PRESS-EXP-02').closest('li')!
    expect(preexistente.className).not.toMatch(/alarm-enter/)
    expect(novo.className).toMatch(/alarm-enter/)
  })

  it('rerender sem mudanca nas chaves nao marca nada como novo', () => {
    const { rerender } = render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)
    rerender(<AlarmPanel alarms={[{ ...ABERTO }]} areaNameByCode={AREA_NAMES} />)
    const li = screen.getByRole('listitem')
    expect(li.className).not.toMatch(/alarm-enter/)
  })

  describe('flash de "novo" sobrevive a re-renders dentro dos 5s (sticky)', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('re-render com as mesmas chaves (ex.: poll de 5s) NAO corta o flash antes do timer; timer remove apos ~5s', () => {
      vi.useFakeTimers()
      const OUTRO: AlarmEvent = { ...ABERTO, id: 2, sensor_code: 'PRESS-EXP-02', timestamp_deteccao: ABERTO.timestamp_deteccao + 60_000 }

      const { rerender } = render(<AlarmPanel alarms={[ABERTO]} areaNameByCode={AREA_NAMES} />)

      // Chega um alarme novo: marca isNew.
      act(() => {
        rerender(<AlarmPanel alarms={[OUTRO, ABERTO]} areaNameByCode={AREA_NAMES} />)
      })
      let novo = screen.getByText('Expurgo · PRESS-EXP-02').closest('li')!
      expect(novo.className).toMatch(/alarm-enter/)

      // Re-render com as MESMAS chaves (simula poll do useAlarms a cada 5s,
      // ou qualquer outro re-render do pai) -- nao deve cortar a animacao.
      act(() => {
        rerender(<AlarmPanel alarms={[{ ...OUTRO }, { ...ABERTO }]} areaNameByCode={AREA_NAMES} />)
      })
      novo = screen.getByText('Expurgo · PRESS-EXP-02').closest('li')!
      expect(novo.className).toMatch(/alarm-enter/)

      // Passados os 5s (+ folga do timer), o flash termina.
      act(() => {
        vi.advanceTimersByTime(5300)
      })
      novo = screen.getByText('Expurgo · PRESS-EXP-02').closest('li')!
      expect(novo.className).not.toMatch(/alarm-enter/)
    })
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
