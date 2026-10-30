import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Topbar } from '../components/Topbar'
import { SensorSelect } from '../components/select/SensorSelect'
import { useECharts } from '../components/useECharts'
import { buildReportChartOption, rotuloBucket } from '../components/reportChartOption'
import { useLiveConnection } from '../lib/useLiveConnection'
import { useThemeColor } from '../lib/useThemeColor'
import { reportApi } from '../lib/api'
import { VIOLACAO_LABEL } from '../lib/violacao'
import type { Granularidade, Report, ReportParams, ReportSensor } from '../lib/api/contracts'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'
const TZ = 'America/Sao_Paulo'
const MAX_SENSORES = 20

// Hoje em Sao Paulo, AAAA-MM-DD (en-CA formata assim).
const hojeSP = () => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date())

const fmtDataHora = (d: Date) =>
  new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    .format(d)
    .replace(',', '')
const fmtNum = (v: number | null) => (v == null ? '—' : v.toLocaleString('pt-BR', { maximumFractionDigits: 2 }))
const fmtDia = (iso: string) => iso.split('-').reverse().join('/')

function rotuloTabela(iso: string, gran: Granularidade): string {
  const [data] = iso.split('T')
  return gran === 'hora' ? `${fmtDia(data)} ${rotuloBucket(iso, gran)}` : gran === 'dia' ? fmtDia(data) : rotuloBucket(iso, gran)
}

// Data local (AAAA-MM-DD) de um instante, em Sao Paulo.
const diaSP = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(d)

// Avisos de mes parcial (granularidade mensal): primeiro/ultimo mes incompleto.
function notasMesParcial(inicio: string, fim: string, gran: Granularidade): string[] {
  if (gran !== 'mes') return []
  const [yi, mi, di] = inicio.split('-').map(Number)
  const [yf, mf, df] = fim.split('-').map(Number)
  const ultimoDia = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate()
  const dd = (n: number) => String(n).padStart(2, '0')
  const fmt = (y: number, m: number, d: number) => `${dd(d)}/${dd(m)}/${y}`
  const parcialIni = di !== 1
  const parcialFim = df !== ultimoDia(yf, mf)
  if (yi === yf && mi === mf) {
    return parcialIni || parcialFim ? [`Mês parcial: dados de ${fmt(yi, mi, di)} a ${fmt(yf, mf, df)}.`] : []
  }
  const notas: string[] = []
  if (parcialIni) notas.push(`Primeiro mês parcial: dados de ${fmt(yi, mi, di)} a ${fmt(yi, mi, ultimoDia(yi, mi))}.`)
  if (parcialFim) notas.push(`Último mês parcial: dados de ${fmt(yf, mf, 1)} a ${fmt(yf, mf, df)}.`)
  return notas
}

const CAMPO_LABEL: Record<string, string> = { limite_min: 'mínimo', limite_max: 'máximo' }

const inputCls =
  'min-h-11 rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]'
const inputStyle = { background: 'var(--color-surface)', border: '1px solid var(--color-line)', color: 'var(--color-ink)' }
const btnCls =
  'min-h-11 rounded-md px-4 text-sm font-semibold outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:opacity-60 motion-reduce:transition-none'
const btnIconCls = `${btnCls} inline-flex items-center gap-2`

function IconeDownload() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 2v8M4.5 6.8 8 10.3l3.5-3.5M2.5 11.5v1.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1.5" />
    </svg>
  )
}

function IconeImpressora() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
      <path d="M4.5 5.5V2h7v3.5M4.5 11.5h-2a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-2M4.5 9.5h7V14h-7z" />
    </svg>
  )
}

const btnPrimary = { background: 'var(--color-primary)', color: 'var(--color-surface)' }
const btnSecondary = { background: 'var(--color-panel)', color: 'var(--color-ink)', border: '1px solid var(--color-line)' }

function ReportChart({ sensor, gran }: { sensor: ReportSensor; gran: Granularidade }) {
  const { el, chart } = useECharts()
  const crit = useThemeColor('--color-crit')
  const primary = useThemeColor('--color-primary')
  useEffect(() => {
    chart.current?.setOption(buildReportChartOption(sensor, gran, { crit, primary }), { notMerge: true })
  }, [sensor, gran, crit, primary, chart])
  return <div ref={el} style={{ width: '100%', height: 260 }} />
}

function SensorReport({ sensor, gran, fim, notas }: { sensor: ReportSensor; gran: Granularidade; fim: string; notas: string[] }) {
  const titleId = `rel-${sensor.sensor_code}`
  const muted = { color: 'var(--color-muted)' }
  return (
    <section
      aria-labelledby={titleId}
      className="rounded-lg p-4"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      <h2 id={titleId} className="text-base font-bold" style={{ color: 'var(--color-ink)' }}>
        {sensor.nome} <span className="font-mono text-sm font-normal" style={muted}>{sensor.sensor_code}</span>
      </h2>
      <p className="text-sm" style={muted}>
        {sensor.site ?? '—'} · Unidade: {sensor.unidade} · Limites:{' '}
        {sensor.limites ? `${fmtNum(sensor.limites.limite_min)} a ${fmtNum(sensor.limites.limite_max)}` : 'não configurados'}
      </p>
      <p className="text-sm" style={muted}>
        Área: {sensor.area ?? '—'} · Localização: {sensor.localizacao ?? 'não informada'}
        {sensor.endereco && <> · Endereço: {sensor.endereco}</>}
      </p>

      {sensor.alteracoes_limite.length > 0 && (
        <ul className="mt-2 space-y-1 rounded-md px-3 py-2 text-sm" style={{ background: 'var(--color-warn-soft)', color: 'var(--color-ink)' }}>
          {sensor.alteracoes_limite.map((a, i) => (
            <li key={i}>
              Limite alterado em {fmtDataHora(new Date(a.quando))} ({CAMPO_LABEL[a.campo] ?? a.campo}: de {fmtNum(a.de)} para {fmtNum(a.para)})
              {diaSP(new Date(a.quando)) > fim && ' — após o período'}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3">
        <ReportChart sensor={sensor} gran={gran} />
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm tabular-nums" style={{ color: 'var(--color-ink)' }}>
          <thead>
            <tr style={muted} className="text-left">
              <th className="py-1 pr-3 font-semibold">Período</th>
              <th className="py-1 pr-3 text-right font-semibold">Média</th>
              <th className="py-1 pr-3 text-right font-semibold">Mín</th>
              <th className="py-1 pr-3 text-right font-semibold">Máx</th>
              <th className="py-1 pr-3 text-right font-semibold">Leituras</th>
              <th className="py-1 font-semibold">Situação</th>
            </tr>
          </thead>
          <tbody>
            {sensor.buckets.map((b) => (
              <tr
                key={b.bucket}
                style={{ borderTop: '1px solid var(--color-line)', background: b.fora_limite ? 'var(--color-crit-soft)' : undefined }}
              >
                <td className="py-1 pr-3">{rotuloTabela(b.bucket, gran)}</td>
                <td className="py-1 pr-3 text-right">{fmtNum(b.avg)}</td>
                <td className="py-1 pr-3 text-right">{fmtNum(b.min)}</td>
                <td className="py-1 pr-3 text-right">{fmtNum(b.max)}</td>
                <td className="py-1 pr-3 text-right">{b.n_ok}{b.n_falha > 0 ? ` (+${b.n_falha} falha)` : ''}</td>
                <td className="py-1">
                  {b.estado === 'sem_dados' ? (
                    <span style={muted}>Sem dados</span>
                  ) : b.estado === 'falha_instrumento' ? (
                    <span style={{ color: 'var(--color-warn)' }}>Falha de instrumento</span>
                  ) : b.fora_limite ? (
                    <span aria-label="fora do limite" className="font-semibold" style={{ color: 'var(--color-crit)' }}>
                      ▲ Fora do limite
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-good)' }}>Conforme</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {notas.map((n) => (
        <p key={n} className="mt-1 text-xs" style={muted}>{n}</p>
      ))}

      <h3 className="mt-4 text-sm font-bold" style={{ color: 'var(--color-ink)' }}>Alarmes no período</h3>
      {sensor.alarmes.length === 0 ? (
        <p className="text-sm" style={muted}>Nenhum alarme.</p>
      ) : (
        <ul className="mt-1 space-y-1 text-sm" style={{ color: 'var(--color-ink)' }}>
          {sensor.alarmes.map((a) => (
            <li key={a.id}>
              {fmtDataHora(new Date(a.timestamp_deteccao))} — {VIOLACAO_LABEL[a.tipo_violacao]} (lido {fmtNum(a.valor_lido)}, limite{' '}
              {fmtNum(a.limite_configurado_snapshot)}) · {a.status}
              {a.data_resolucao != null && ` em ${fmtDataHora(new Date(a.data_resolucao))}`}
              {a.usuario_responsavel && ` por ${a.usuario_responsavel}`}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function RelatoriosPage() {
  const liveState = useLiveConnection()
  const [inicio, setInicio] = useState(hojeSP)
  const [fim, setFim] = useState(hojeSP)
  // Nenhum sensor pre-selecionado: o usuario escolhe.
  const [selecionados, setSelecionados] = useState<string[]>([])
  const [erroJanela, setErroJanela] = useState<string | null>(null)
  const [gerado, setGerado] = useState<ReportParams | null>(null)

  const report = useMutation<Report, Error, ReportParams>({ mutationFn: (p) => reportApi.getReport(p) })
  const pdf = useMutation<Blob, Error, { params: ReportParams; modo: 'baixar' | 'imprimir'; janela: Window | null }>({
    mutationFn: ({ params }) => reportApi.getReportPdf(params),
    onError: (_e, { janela }) => janela?.close(),
    onSuccess: (blob, { params, modo, janela }) => {
      const url = URL.createObjectURL(blob)
      if (modo === 'baixar') {
        const a = document.createElement('a')
        a.href = url
        a.download = `relatorio_${params.inicio}_${params.fim}.pdf`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
      } else {
        // Janela aberta de forma sincrona no clique (senao o popup e bloqueado).
        if (janela) janela.location.href = url
        // A nova aba ainda precisa carregar o blob: revoga depois.
        setTimeout(() => URL.revokeObjectURL(url), 60_000)
      }
    },
  })

  const gerar = (e: React.FormEvent) => {
    e.preventDefault()
    const params = { sensores: selecionados, inicio, fim }
    setGerado(params)
    setErroJanela(null)
    pdf.reset()
    report.mutate(params)
  }

  const exportar = (modo: 'baixar' | 'imprimir') => {
    if (!gerado) return
    setErroJanela(null)
    let janela: Window | null = null
    if (modo === 'imprimir') {
      janela = window.open('', '_blank')
      if (!janela) {
        setErroJanela('Não foi possível abrir a janela de impressão. Permita pop-ups para este site e tente de novo.')
        return
      }
    }
    pdf.mutate({ params: gerado, modo, janela })
  }

  const erro = report.error?.message ?? pdf.error?.message ?? erroJanela
  return (
    <div className="min-h-screen" style={{ background: 'var(--color-panel)' }}>
      <Topbar healthy={false} unitName={UNIT_NAME} liveState={liveState} />
      <main className="mx-auto max-w-6xl space-y-4 px-6 py-6">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-ink)' }}>Relatório de período</h1>

        <form onSubmit={gerar} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--color-muted)' }}>
            Data início
            <input type="date" required value={inicio} max={fim} onChange={(e) => setInicio(e.target.value)} className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--color-muted)' }}>
            Data fim
            <input type="date" required value={fim} min={inicio} onChange={(e) => setFim(e.target.value)} className={inputCls} style={inputStyle} />
          </label>
          <div className="min-w-[260px] flex-1">
            <SensorSelect multiple label="Sensores" value={selecionados} onChange={setSelecionados} />
          </div>
          <button type="submit" className={btnCls} style={btnPrimary} disabled={selecionados.length === 0 || selecionados.length > MAX_SENSORES || report.isPending}>
            Gerar
          </button>
        </form>

        {selecionados.length > MAX_SENSORES && (
          <p className="text-sm" style={{ color: 'var(--color-warn)' }}>Máximo de {MAX_SENSORES} sensores por relatório.</p>
        )}
        {erro && (
          <p role="alert" className="rounded-md px-3 py-2 text-sm" style={{ background: 'var(--color-crit-soft)', color: 'var(--color-crit)' }}>
            {erro}
          </p>
        )}
        {report.isPending && <p role="status" className="text-sm" style={{ color: 'var(--color-muted)' }}>Gerando relatório…</p>}

        {report.data && gerado && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
                {fmtDia(report.data.inicio)} a {fmtDia(report.data.fim)} · emitido em {fmtDataHora(new Date(report.data.emitido_em))} por {report.data.emissor}
              </p>
              <div className="ml-auto flex gap-2">
                <button type="button" className={btnIconCls} style={btnSecondary} disabled={pdf.isPending} onClick={() => exportar('baixar')}>
                  <IconeDownload />
                  Baixar PDF
                </button>
                <button type="button" className={btnIconCls} style={btnSecondary} disabled={pdf.isPending} onClick={() => exportar('imprimir')}>
                  <IconeImpressora />
                  Imprimir
                </button>
              </div>
            </div>
            {report.data.sensores.map((s) => (
              <SensorReport
                key={s.sensor_code}
                sensor={s}
                gran={report.data.granularidade}
                fim={report.data.fim}
                notas={notasMesParcial(report.data.inicio, report.data.fim, report.data.granularidade)}
              />
            ))}
          </>
        )}
      </main>
    </div>
  )
}
