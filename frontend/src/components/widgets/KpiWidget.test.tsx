import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KpiWidget } from './KpiWidget'
import { statusTextColor } from '../statusVisuals'

vi.mock('../../lib/queries', () => ({
  useSensorMeta: () => ({ data: undefined }),
}))

const mockUseLiveTail = vi.fn()
vi.mock('../../lib/useLiveTail', () => ({
  useLiveTail: (code: string) => mockUseLiveTail(code),
}))

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('KpiWidget', () => {
  it('renderiza o label quando fornecido', () => {
    mockUseLiveTail.mockReturnValue({ last: null })
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" label="Pressão Expurgo" />)
    expect(screen.getByText('Pressão Expurgo')).toBeInTheDocument()
  })

  it('mostra o sensorCode como fallback de título quando sem label', () => {
    mockUseLiveTail.mockReturnValue({ last: null })
    renderWithClient(<KpiWidget sensorCode="PRESS-EXP-01" />)
    expect(screen.getByText(/PRESS-EXP-01/)).toBeInTheDocument()
  })

  it('sem last (sem leitura) -> valor "—", cor de unknown, mesmo com override setado', () => {
    mockUseLiveTail.mockReturnValue({ last: null })
    renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
    const valor = screen.getByText('—')
    expect(valor.style.color).toBe('var(--color-ink)')
  })

  describe('sem override (limiteMin/limiteMax ausentes) — comportamento idêntico ao atual', () => {
    it('alarm_state ok -> --color-ink', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 10, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" />)
      expect(screen.getByText('10').style.color).toBe('var(--color-ink)')
    })

    it('alarm_state crit -> cor de crit', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 10, alarm_state: 'crit' } })
      renderWithClient(<KpiWidget sensorCode="S1" />)
      expect(screen.getByText('10').style.color).toBe(statusTextColor('crit'))
    })
  })

  describe('override de threshold (limiteMin/limiteMax) — semântica max(), só escala', () => {
    it('valor FORA da faixa -> crit mesmo com alarm_state ok (escala)', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 100, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      expect(screen.getByText('100').style.color).toBe(statusTextColor('crit'))
    })

    it('valor DENTRO da faixa mas alarm_state crit -> continua crit (override não rebaixa)', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 25, alarm_state: 'crit' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      expect(screen.getByText('25').style.color).toBe(statusTextColor('crit'))
    })

    it('valor DENTRO da faixa e alarm_state ok -> --color-ink', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 25, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      expect(screen.getByText('25').style.color).toBe('var(--color-ink)')
    })

    it('guarda anti-regressão A2: override "dentro da faixa" não pinta de verde alarm_state warn', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 25, alarm_state: 'warn' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      const cor = screen.getByText('25').style.color
      expect(cor).toBe(statusTextColor('warn'))
      expect(cor).not.toBe('var(--color-ink)')
    })

    it('guarda anti-regressão A2: override "dentro da faixa" não pinta de verde alarm_state crit', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 25, alarm_state: 'crit' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      const cor = screen.getByText('25').style.color
      expect(cor).toBe(statusTextColor('crit'))
      expect(cor).not.toBe('var(--color-ink)')
    })

    it('valor FORA da faixa com alarm_state warn -> continua crit (escala de warn, não só de ok)', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 100, alarm_state: 'warn' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} limiteMax={50} />)
      expect(screen.getByText('100').style.color).toBe(statusTextColor('crit'))
    })

    it('só limiteMin setado (limiteMax ausente) já conta como override', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: -5, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" limiteMin={0} />)
      expect(screen.getByText('-5').style.color).toBe(statusTextColor('crit'))
    })
  })
})
