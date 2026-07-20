import { describe, it, expect } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { AlarmsWidget } from './AlarmsWidget'
import type { AlarmEvent, SensorMeta } from '../../lib/types'

function sensor(areaCode: string, areaName: string): SensorMeta {
  return {
    sensor_code: `SNR-${areaCode}`,
    name: `Sensor ${areaCode}`,
    unidade: 'C',
    protocolo_origem: '4-20ma',
    measurement_type: { code: 'temp', name: 'Temperatura' },
    area: { area_code: areaCode, name: areaName, category: 'sala' },
  }
}

// Superset dos area_codes usados neste arquivo (a, b, c, PREPARO) — cobre
// tanto os testes novos de filtro quanto os testes pre-existentes de scope,
// que usam 'PREPARO' como area_code default em makeAlarms(). O universo de
// chips (todasAreas) vem de useSensors, entao qualquer area_code usado num
// alarme de teste precisa aparecer aqui, senao o alarme fica invisivel por
// nao pertencer a nenhum chip (default nunca o ativa).
const SITE_SENSORS: SensorMeta[] = [
  sensor('a', 'Área A'),
  sensor('b', 'Área B'),
  sensor('c', 'Área C'),
  sensor('PREPARO', 'Preparo'),
]

// Semeia o cache de ['alarms'] e ['sensors'] com staleTime: Infinity para que
// os hooks reais (useAlarms com refetchInterval: 5000, useSensors) nao
// disparem um refetch em background que sobrescreveria os fixtures semeados.
function renderWithAlarms(
  alarms: AlarmEvent[],
  props: { scope: 'site' | 'area'; areaCodes: string[] } = { scope: 'site', areaCodes: [] },
  sensors: SensorMeta[] = SITE_SENSORS,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['alarms'], alarms)
  qc.setQueryData(['sensors'], sensors)
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

  it('default scope="area" com areaCodes=[a,b]: chips a,b ativos, demais (c) presente e inativo', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a', 'b'] })

    const chipA = await screen.findByRole('button', { name: 'Área A' })
    const chipB = screen.getByRole('button', { name: 'Área B' })
    const chipC = screen.getByRole('button', { name: 'Área C' })
    expect(chipA).toHaveAttribute('aria-pressed', 'true')
    expect(chipB).toHaveAttribute('aria-pressed', 'true')
    expect(chipC).toHaveAttribute('aria-pressed', 'false')

    expect(screen.getByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
    expect(screen.queryByText(/SENSOR-C/)).not.toBeInTheDocument()
  })

  it('default scope="site": todos os chips ativos, todos os alarmes exibidos', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
    renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

    for (const name of ['Área A', 'Área B', 'Área C']) {
      expect(await screen.findByRole('button', { name })).toHaveAttribute('aria-pressed', 'true')
    }
    expect(screen.getByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-C/)).toBeInTheDocument()
  })

  it('clicar chip inativo (c) passa a mostrar alarmes de c', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-C', 'c')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a'] })

    expect(screen.queryByText(/SENSOR-C/)).not.toBeInTheDocument()
    const chipC = await screen.findByRole('button', { name: 'Área C' })
    await userEvent.click(chipC)

    expect(chipC).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByText(/SENSOR-C/)).toBeInTheDocument()
  })

  it('clicar chip ativo remove os alarmes daquela área', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a', 'b'] })

    const chipA = await screen.findByRole('button', { name: 'Área A' })
    await userEvent.click(chipA)

    expect(chipA).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText(/SENSOR-A/)).not.toBeInTheDocument()
    expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
  })

  it('desativar todas as áreas (múltiplos chips ativos) mostra "Nenhuma área selecionada" (não "Nenhum alarme ativo.")', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a', 'b'] }, [
      sensor('a', 'Área A'),
      sensor('b', 'Área B'),
    ])

    const chipA = await screen.findByRole('button', { name: 'Área A' })
    const chipB = screen.getByRole('button', { name: 'Área B' })
    expect(chipA).toHaveAttribute('aria-pressed', 'true')
    expect(chipB).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(chipA)
    await userEvent.click(chipB)

    expect(chipA).toHaveAttribute('aria-pressed', 'false')
    expect(chipB).toHaveAttribute('aria-pressed', 'false')
    expect(await screen.findByText('Nenhuma área selecionada')).toBeInTheDocument()
    expect(screen.queryByText('Nenhum alarme ativo.')).not.toBeInTheDocument()
    expect(screen.queryByText(/SENSOR-A/)).not.toBeInTheDocument()
    expect(screen.queryByText(/SENSOR-B/)).not.toBeInTheDocument()
  })

  it('config legada resolvida para areaCodes=["a"]: chip a ativo por default', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a'] })

    expect(await screen.findByRole('button', { name: 'Área A' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Área B' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.queryByText(/SENSOR-B/)).not.toBeInTheDocument()
  })

  it('modal "Ver mais" recebe os alarmes já filtrados pelo chip', async () => {
    const alarms = [...makeAlarms(9, 'a'), alarme('SENSOR-C-EXTRA', 'c')]
    renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a'] })

    const verMaisButton = await screen.findByRole('button', { name: /Ver mais/ })
    await userEvent.click(verMaisButton)

    const dialog = await screen.findByRole('dialog', { name: 'Todos os alarmes' })
    expect(within(dialog).queryByText(/SENSOR-C-EXTRA/)).not.toBeInTheDocument()
  })

  // Regressao CRITICAL (produto medico): useAlarms e useSensors sao queries
  // independentes, sem ordem garantida. Se useSensors ainda nao resolveu (ou
  // retorna vazio) enquanto useAlarms ja tem dados reais, o universo de areas
  // (todasAreas) nao pode depender so de useSensors -- senao defaultAtivas
  // fica vazio e em scope='site' TODOS os alarmes reais somem, exibindo
  // "Nenhum alarme ativo." (all-clear falso) no exato momento em que o
  // alarme mais precisa aparecer.
  it('CRITICAL: useSensors vazio + useAlarms com alarmes reais (scope=site) -- alarmes aparecem, nao all-clear falso', async () => {
    const alarms = [alarme('SENSOR-X', 'x'), alarme('SENSOR-Y', 'y')]
    renderWithAlarms(alarms, { scope: 'site', areaCodes: [] }, [])

    expect(await screen.findByText(/SENSOR-X/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-Y/)).toBeInTheDocument()
    expect(screen.queryByText('Nenhum alarme ativo.')).not.toBeInTheDocument()

    // chips das areas dos alarmes devem existir mesmo sem sensor correspondente
    expect(screen.getByRole('button', { name: 'x' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'y' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('alarme com area_code sem sensor correspondente tem chip proprio e aparece em scope=site', async () => {
    const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-ORFAO', 'orfao')]
    renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

    expect(await screen.findByText(/SENSOR-A/)).toBeInTheDocument()
    expect(screen.getByText(/SENSOR-ORFAO/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'orfao' })).toHaveAttribute('aria-pressed', 'true')
  })

  describe('chip "Todas" (toggle-all)', () => {
    it('está presente e é o primeiro botão da linha de filtro', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const grupo = await screen.findByRole('group', { name: 'Filtro de áreas' })
      const botoes = within(grupo).getAllByRole('button')
      expect(botoes[0]).toHaveTextContent('Todas')
    })

    it('default scope="site" (todas ativas) -> "Todas" aria-pressed="true"', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const todas = await screen.findByRole('button', { name: 'Todas' })
      expect(todas).toHaveAttribute('aria-pressed', 'true')
    })

    it('tap em "Todas" com todas ativas -> limpa (chips de área false, painel "Nenhuma área selecionada")', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const todas = await screen.findByRole('button', { name: 'Todas' })
      await userEvent.click(todas)

      expect(todas).toHaveAttribute('aria-pressed', 'false')
      for (const name of ['Área A', 'Área B', 'Área C']) {
        expect(screen.getByRole('button', { name })).toHaveAttribute('aria-pressed', 'false')
      }
      expect(await screen.findByText('Nenhuma área selecionada')).toBeInTheDocument()
    })

    it('a partir de "nenhuma", tap em "Todas" -> ativa todas', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
      renderWithAlarms(
        alarms,
        { scope: 'area', areaCodes: ['a', 'b'] },
        [sensor('a', 'Área A'), sensor('b', 'Área B')],
      )

      const chipA = await screen.findByRole('button', { name: 'Área A' })
      const chipB = screen.getByRole('button', { name: 'Área B' })
      await userEvent.click(chipA)
      await userEvent.click(chipB)
      expect(chipA).toHaveAttribute('aria-pressed', 'false')
      expect(chipB).toHaveAttribute('aria-pressed', 'false')

      const todas = screen.getByRole('button', { name: 'Todas' })
      expect(todas).toHaveAttribute('aria-pressed', 'false')
      await userEvent.click(todas)

      expect(todas).toHaveAttribute('aria-pressed', 'true')
      expect(chipA).toHaveAttribute('aria-pressed', 'true')
      expect(chipB).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByText(/SENSOR-A/)).toBeInTheDocument()
      expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
    })

    it('desativar 1 área -> "Todas" aria-pressed="mixed"', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const chipA = await screen.findByRole('button', { name: 'Área A' })
      await userEvent.click(chipA)

      const todas = screen.getByRole('button', { name: 'Todas' })
      expect(todas).toHaveAttribute('aria-pressed', 'mixed')
    })

    it('isolar em 2 toques: tap "Todas" (limpa) -> tap área X -> só alarmes de X; "Todas" volta a "mixed"', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const todas = await screen.findByRole('button', { name: 'Todas' })
      await userEvent.click(todas)

      const chipB = screen.getByRole('button', { name: 'Área B' })
      await userEvent.click(chipB)

      expect(chipB).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByRole('button', { name: 'Área A' })).toHaveAttribute('aria-pressed', 'false')
      expect(screen.getByRole('button', { name: 'Área C' })).toHaveAttribute('aria-pressed', 'false')
      expect(todas).toHaveAttribute('aria-pressed', 'mixed')
      expect(screen.queryByText(/SENSOR-A/)).not.toBeInTheDocument()
      expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
      expect(screen.queryByText(/SENSOR-C/)).not.toBeInTheDocument()
    })

    it('voltar a todas em 1 toque: de subconjunto, tap "Todas" -> todos os alarmes de volta', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b'), alarme('SENSOR-C', 'c')]
      renderWithAlarms(alarms, { scope: 'site', areaCodes: [] })

      const chipA = await screen.findByRole('button', { name: 'Área A' })
      await userEvent.click(chipA)

      const todas = screen.getByRole('button', { name: 'Todas' })
      expect(todas).toHaveAttribute('aria-pressed', 'mixed')
      await userEvent.click(todas)

      expect(todas).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByText(/SENSOR-A/)).toBeInTheDocument()
      expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
      expect(screen.getByText(/SENSOR-C/)).toBeInTheDocument()
    })

    it('tap numa área continua sendo liga/desliga individual (não regride)', async () => {
      const alarms = [alarme('SENSOR-A', 'a'), alarme('SENSOR-B', 'b')]
      renderWithAlarms(alarms, { scope: 'area', areaCodes: ['a', 'b'] })

      const chipA = await screen.findByRole('button', { name: 'Área A' })
      await userEvent.click(chipA)

      expect(chipA).toHaveAttribute('aria-pressed', 'false')
      expect(screen.queryByText(/SENSOR-A/)).not.toBeInTheDocument()
      expect(screen.getByText(/SENSOR-B/)).toBeInTheDocument()
    })
  })
})
