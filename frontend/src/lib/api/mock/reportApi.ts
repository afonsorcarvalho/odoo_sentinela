import type { ReportApi, ReportParams, Report, ReportBucket, ReportSensor, Granularidade } from '../contracts'
import { SENSORS, THRESHOLDS } from './fixtures'

const MS_DIA = 86_400_000

function addDias(iso: string, n: number): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + n))
}

function granularidade(inicio: string, fim: string): Granularidade {
  if (inicio === fim) return 'hora'
  const dias = Math.round((addDias(fim, 0).getTime() - addDias(inicio, 0).getTime()) / MS_DIA) + 1
  return dias <= 62 ? 'dia' : 'mes'
}

const p2 = (n: number) => String(n).padStart(2, '0')
// Rotulos em horario local fixo -03:00 (Sao Paulo, sem DST desde 2019).
const rotulo = (d: Date, comHora: boolean) =>
  `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${comHora ? p2(d.getUTCHours()) : '00'}:00:00-03:00`

function inicios(inicio: string, fim: string, gran: Granularidade): string[] {
  const out: string[] = []
  if (gran === 'hora') {
    const base = addDias(inicio, 0)
    for (let h = 0; h < 24; h++) out.push(rotulo(new Date(base.getTime() + h * 3_600_000), true))
  } else if (gran === 'dia') {
    for (let d = addDias(inicio, 0); d <= addDias(fim, 0); d = new Date(d.getTime() + MS_DIA)) out.push(rotulo(d, false))
  } else {
    const f = addDias(fim, 0)
    let d = new Date(Date.UTC(addDias(inicio, 0).getUTCFullYear(), addDias(inicio, 0).getUTCMonth(), 1))
    while (d <= f) {
      out.push(rotulo(d, false))
      d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))
    }
  }
  return out
}

// Determinístico: sem Date.now/random. i=1 -> sem_dados; i=2 -> falha_instrumento;
// i=3 -> fora_limite (acima do max, so se o sensor tem limites); demais ok dentro da faixa.
function bucketMock(label: string, i: number, min: number, max: number, temLimites: boolean): ReportBucket {
  const mid = (min + max) / 2
  const amp = (max - min) / 4
  if (i === 1) return { bucket: label, avg: null, min: null, max: null, n_ok: 0, n_falha: 0, estado: 'sem_dados', fora_limite: false }
  if (i === 2) return { bucket: label, avg: null, min: null, max: null, n_ok: 0, n_falha: 5, estado: 'falha_instrumento', fora_limite: false }
  const avg = mid + amp * Math.sin(i)
  const fora = temLimites && i === 3
  return {
    bucket: label,
    avg: +avg.toFixed(2),
    min: +(avg - amp / 2).toFixed(2),
    max: +(fora ? max + amp : avg + amp / 2).toFixed(2),
    n_ok: 60, n_falha: 0, estado: 'ok', fora_limite: fora,
  }
}

function sensorMock(code: string, gran: Granularidade, inicio: string, fim: string): ReportSensor {
  const meta = SENSORS.find((s) => s.sensor_code === code) ?? SENSORS[0]
  const th = THRESHOLDS[meta.sensor_code]
  const min = th?.limite_min ?? 0
  const max = th?.limite_max ?? 100
  return {
    sensor_code: meta.sensor_code,
    nome: meta.name,
    unidade: meta.unidade,
    site: 'Site Mock',
    limites: th ? { limite_min: min, limite_max: max } : null,
    // Uma alteracao e um alarme de amostra (so p/ sensores com limite) para a
    // UI ser exercitavel em modo mock. Instantes no primeiro dia do periodo.
    alteracoes_limite: th
      ? [{ quando: addDias(inicio, 0).toISOString().replace('T00:00:00.000Z', 'T13:30:00+00:00'), campo: 'limite_max', de: max - 1, para: max }]
      : [],
    buckets: inicios(inicio, fim, gran).map((l, i) => bucketMock(l, i, min, max, !!th)),
    alarmes: th
      ? [{
          id: 9001, sensor_code: meta.sensor_code, area_code: meta.area.area_code,
          timestamp_deteccao: addDias(inicio, 0).getTime() + 6 * 3_600_000, timestamp_resolucao_sensor: null,
          valor_lido: max + 1, tipo_violacao: 'acima_limite', limite_configurado_snapshot: max,
          status: 'resolvido', usuario_responsavel: 'Usuário Mock',
          data_resolucao: addDias(inicio, 0).getTime() + 7 * 3_600_000, observacoes: null,
        }]
      : [],
  }
}

export const mockReportApi: ReportApi = {
  async getReport(p: ReportParams): Promise<Report> {
    if (p.fim < p.inicio) throw new Error('fim anterior ao início')
    const gran = granularidade(p.inicio, p.fim)
    return {
      inicio: p.inicio, fim: p.fim, granularidade: gran, fuso: 'America/Sao_Paulo',
      emitido_em: '2026-01-01T12:00:00+00:00', emissor: 'Usuário Mock',
      sensores: p.sensores.map((c) => sensorMock(c, gran, p.inicio, p.fim)),
    }
  },
  async getReportPdf(): Promise<Blob> {
    return new Blob(['%PDF-1.4 mock'], { type: 'application/pdf' })
  },
}
