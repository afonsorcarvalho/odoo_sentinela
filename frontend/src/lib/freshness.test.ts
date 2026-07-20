import { describe, it, expect } from 'vitest'
import { freshness, formatAge, DEFAULT_STALE_MS, DEFAULT_OFFLINE_MS } from './freshness'
import type { LivePoint } from './types'

function point(ts: number): LivePoint {
  return { sensor_code: 'x', ts, value: 1, alarm_state: 'ok' }
}

describe('freshness', () => {
  const now = 1_800_000_000_000

  it('live === undefined -> never (nenhum LivePoint recebido)', () => {
    expect(freshness(undefined, now)).toBe('never')
  })

  it('ageMs bem dentro do staleMs -> fresh', () => {
    expect(freshness(point(now - 1000), now)).toBe('fresh')
    expect(freshness(point(now - DEFAULT_STALE_MS + 1), now)).toBe('fresh')
  })

  it('fronteira exata ageMs === staleMs -> fresh (determinístico)', () => {
    expect(freshness(point(now - DEFAULT_STALE_MS), now)).toBe('fresh')
  })

  it('staleMs < ageMs -> stale', () => {
    expect(freshness(point(now - DEFAULT_STALE_MS - 1), now)).toBe('stale')
  })

  it('fronteira exata ageMs === offlineMs -> stale (determinístico)', () => {
    expect(freshness(point(now - DEFAULT_OFFLINE_MS), now)).toBe('stale')
  })

  it('ageMs > offlineMs -> offline', () => {
    expect(freshness(point(now - DEFAULT_OFFLINE_MS - 1), now)).toBe('offline')
  })

  it('respeita cfg custom de staleMs/offlineMs (sem depender dos defaults)', () => {
    expect(freshness(point(now - 100), now, { staleMs: 50, offlineMs: 200 })).toBe('stale')
    expect(freshness(point(now - 200), now, { staleMs: 50, offlineMs: 200 })).toBe('stale')
    expect(freshness(point(now - 201), now, { staleMs: 50, offlineMs: 200 })).toBe('offline')
    expect(freshness(point(now - 50), now, { staleMs: 50, offlineMs: 200 })).toBe('fresh')
  })
})

describe('formatAge', () => {
  it('90s -> "há 1 min"', () => {
    expect(formatAge(90_000)).toBe('há 1 min')
  })

  it('6 min -> "há 6 min"', () => {
    expect(formatAge(6 * 60_000)).toBe('há 6 min')
  })

  it('80 min (> 1h) -> "há 1 h 20 min"', () => {
    expect(formatAge(80 * 60_000)).toBe('há 1 h 20 min')
  })

  it('exatamente 1h -> sem minutos residuais', () => {
    expect(formatAge(60 * 60_000)).toBe('há 1 h')
  })

  it('abaixo de 1 min -> segundos (caminho raro: fresh não mostra badge)', () => {
    expect(formatAge(30_000)).toBe('há 30 s')
  })
})
