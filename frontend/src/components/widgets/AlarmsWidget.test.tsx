import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { AlarmsWidget } from './AlarmsWidget'
import type { AlarmEvent } from '../../lib/types'

// Semeia o cache de ['alarms'] com staleTime: Infinity para que o useAlarms()
// (refetchInterval: 5000, hook real) nao dispare um refetch em background que
// sobrescreveria os alarmes semeados com o fixture do mock.
function renderWithAlarms(alarms: AlarmEvent[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['alarms'], alarms)
  return render(
    <QueryClientProvider client={qc}>
      <AlarmsWidget scope="site" />
    </QueryClientProvider>,
  )
}

// VISIBLE_LIMIT em AlarmPanel.tsx e 8; o botao "Ver mais" so aparece quando
// restantes (alarms.length - 8) > 0, ou seja, com 9+ alarmes.
function makeAlarms(count: number): AlarmEvent[] {
  return Array.from({ length: count }, (_, i) => ({
    id: 1000 + i,
    sensor_code: `TEMP-PRE-0${i + 1}`,
    area_code: 'PREPARO',
    tipo_violacao: 'acima_limite',
    status: 'aberto',
    timestamp_deteccao: 1_700_000_000_000 - i * 60_000,
    timestamp_resolucao_sensor: null,
    valor_lido: 24 + i,
    limite_configurado_snapshot: 23,
    usuario_responsavel: null,
    data_resolucao: null,
    observacoes: null,
  }))
}

describe('AlarmsWidget', () => {
  it('abre o modal de alarmes ao clicar em "Ver mais"', async () => {
    renderWithAlarms(makeAlarms(9))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    const verMaisButton = await screen.findByRole('button', { name: /Ver mais/ })
    await userEvent.click(verMaisButton)

    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Todos os alarmes' })).toBeInTheDocument(),
    )
  })
})
