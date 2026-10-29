import type { ReportApi, ReportParams, Report } from '../contracts'
import { authFetchJson, authFetchBlob } from './http'

function query(p: ReportParams): string {
  const qs = new URLSearchParams({ sensores: p.sensores.join(','), inicio: p.inicio, fim: p.fim })
  return qs.toString()
}

export const realReportApi: ReportApi = {
  getReport: (p) => authFetchJson<Report>(`/relatorio?${query(p)}`),
  getReportPdf: (p) => authFetchBlob(`/relatorio.pdf?${query(p)}`),
}
