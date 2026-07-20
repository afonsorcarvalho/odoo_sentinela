import type { FreshnessTier } from './freshness'
import type { StatusResult } from './status'
import type { LivePoint, SensorMeta, Threshold } from './types'

// Estado a exibir para 1 sensor. Sem threshold configurado (ou sem dado ao
// vivo ainda) -> 'unknown' ("Sem limite"), MESMO que o feed reporte
// alarm_state 'ok' internamente — a convencao do liveApi mapeia
// 'unknown'->'ok' na emissao (porque LivePoint.alarm_state nao tem variante
// 'unknown'); aqui reconstruimos a distincao a partir do threshold, que e a
// fonte de verdade sobre "esta configurado" e a UI PRECISA mostrar
// corretamente (ver Global Constraints do plano).
export function sensorDisplayState(
  threshold: Threshold | null,
  live: LivePoint | undefined,
): StatusResult['state'] {
  if (!threshold || !live) return 'unknown'
  return live.alarm_state
}

const SEVERITY: Record<StatusResult['state'], number> = { unknown: 0, ok: 1, warn: 2, crit: 3 }

// Pior estado entre varios sensores (crit > warn > ok > unknown). Array vazio
// -> 'unknown' (nada para agregar).
export function worstAlarmState(states: StatusResult['state'][]): StatusResult['state'] {
  if (states.length === 0) return 'unknown'
  return states.reduce((worst, s) => (SEVERITY[s] > SEVERITY[worst] ? s : worst), states[0])
}

// Entrada por sensor para a agregacao da area (ver areaAggregateState).
// `freshness` aqui e o freshness JA EFETIVO: quem chama (AreaCard) decide se
// um 'never' deve ser tratado como 'offline' apos a janela de graca -- esta
// funcao so olha o valor que recebe, sem conhecer relogio/graca.
export type SensorAggregateInput = { display: StatusResult['state']; freshness: FreshnessTier }

// Agregacao da area (guarda de regressao da razao de ser da feature A2):
// um sensor com freshness 'offline' forca sua contribuicao para a agregacao
// a ser NO MINIMO 'warn', mesmo que o displayState dele seja 'ok' ou
// 'unknown' (sem threshold). Sem isso, um sensor morto sem limite configurado
// contribuiria 'unknown' -- a severidade MAIS BAIXA -- e a area agregaria
// para verde/neutro com um sensor silencioso. 'stale' NAO altera a
// contribuicao nesta fase (so vira badge por-sensor em T3): o offline e o
// unico tier que escala a agregacao, e escala para 'warn' (nao 'crit') --
// default conservador de fase 1 (ver doc, "Fora de escopo").
//
// Reusa worstAlarmState para a ordenacao crit>warn>ok>unknown em vez de
// reimplementar SEVERITY aqui: a contribuicao de um sensor offline e
// worstAlarmState([display, 'warn']) (isto e, max(display, 'warn') na mesma
// ordem), e o resultado final e o pior entre todas as contribuicoes.
export function areaAggregateState(perSensor: SensorAggregateInput[]): StatusResult['state'] {
  const contributions = perSensor.map(({ display, freshness }) =>
    freshness === 'offline' ? worstAlarmState([display, 'warn']) : display,
  )
  return worstAlarmState(contributions)
}

export type AreaGroup = { area: SensorMeta['area']; sensors: SensorMeta[] }

// Agrupa sensores por area_code, preservando a ordem de primeira ocorrencia
// (nao ordena alfabeticamente — a ordem de listSensors() e a ordem de
// exibicao).
export function groupSensorsByArea(sensors: SensorMeta[]): AreaGroup[] {
  const map = new Map<string, AreaGroup>()
  for (const s of sensors) {
    const key = s.area.area_code
    const existing = map.get(key)
    if (existing) existing.sensors.push(s)
    else map.set(key, { area: s.area, sensors: [s] })
  }
  return [...map.values()]
}
