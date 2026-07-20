import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { AlarmsWidget } from './AlarmsWidget'
import type { AlarmEvent } from '../../lib/types'

// Semeia o cache de ['alarms'] com staleTime: Infinity para que o useAlarms()
// (refetchInterval: 5000, hook real) nao dispare um refetch em background que
// sobrescreveria os alarmes semeados com o fixture do mock.
function renderWithAlarms(
  alarms: AlarmEvent[],
  props: { scope: 'site' | 'area'; areaCodes: string[] } = { scope: 'site', areaCodes: [] },
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['alarms'], alarms)
  return render(
    <QueryClientProvider client={qc}>
      <AlarmsWidget scope={props.scope} areaCodes={props.areaCodes} />
    </QueryClientProvider>,
  )
}

// VISIBLE_LIMIT em AlarmPanel.tsx e 8; o botao "Ver mais" so aparece quando
// restantes (alarms.length - 8) > 0, ou seja, com 9+ alarmes.
function makeAlarms(count: number, areaCode = 'PREPARO'): AlarmEvent[] {
  return Array.from({ length: count }, (_, i) => ({
    id: 1000 + i,
    sensor_code: `TEMP-PRE-0${i + 1}`,
    area_code: areaCode,
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

// alarme único, identificável por sensor_code, numa área específica.
// id incremental (não deriva de sensorCode) para nunca colidir entre chamadas
// no mesmo teste — id duplicado gera `key` duplicada no AlarmPanel (React.map).
let alarmeIdSeq = 1
function alarme(sensorCode: string, areaCode: string): AlarmEvent {
  return {
    id: alarmeIdSeq++,
    sensor_code: sensorCode,
    area_code: areaCode,
    tipo_violacao: 'acima_limite',
    status: 'aberto',
    timestamp_deteccao: 1_700_000_000_000,
    timestamp_resolucao_sensor: null,
    valor_lido: 30,
    limite_configurado_snapshot: 23,
    usuario_responsavel: null,
    data_resolucao: null,
    observacoes: null,
  }
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

  it('scope="area" com areaCodes=[a,b] mostra só alarmes de a e b (exclui c)', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a', 'b'] })

    expect(await screen.findByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
    expect(screen.queryByText(/SENSOR-C/)).not.toBeInTheDocument()
  })

  it('scope="area" com areaCodes=[] mostra todos (fallback site)', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: [] })

    expect(await screen.findByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
  })

  it('scope="site" mostra todos, areaCodes é ignorado', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
    renderWithAlarms(alarms, { scope: 'site', areaCodes: ['a'] })

    expect(await screen.findByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
  })
})
