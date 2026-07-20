import { useEffect, useState } from 'react'

const DEFAULT_INTERVAL_MS = 30_000

type Listener = () => void

// Relogio compartilhado: 1 setInterval POR intervalMs distinto, ref-contado
// entre assinantes -- mesmo padrao de multiplexacao do EventSource em
// real/liveApi.ts (ensureSharedSource/closeSharedSourceIfIdle). Evita um
// timer por card quando varias instancias de AreaCard chamam useNow() com o
// mesmo intervalMs; a conexao (aqui, o interval) so fecha quando o ultimo
// inscrito sai.
type ClockEntry = {
  timer: ReturnType<typeof setInterval>
  listeners: Set<Listener>
}
const clocks = new Map<number, ClockEntry>()

function ensureClock(intervalMs: number): ClockEntry {
  const existing = clocks.get(intervalMs)
  if (existing) return existing

  const listeners = new Set<Listener>()
  const timer = setInterval(() => {
    listeners.forEach((cb) => cb())
  }, intervalMs)
  const entry: ClockEntry = { timer, listeners }
  clocks.set(intervalMs, entry)
  return entry
}

function releaseClock(intervalMs: number, listener: Listener): void {
  const entry = clocks.get(intervalMs)
  if (!entry) return
  entry.listeners.delete(listener)
  if (entry.listeners.size === 0) {
    clearInterval(entry.timer)
    clocks.delete(intervalMs)
  }
}

// Devolve Date.now(), atualizado a cada intervalMs por um unico interval
// compartilhado (ver ensureClock acima). Forca re-render periodico mesmo
// sem nenhum evento novo -- e o que permite freshness() reavaliar a idade de
// um sensor silencioso (fresh -> stale -> offline) so pelo relogio andar.
export function useNow(intervalMs: number = DEFAULT_INTERVAL_MS): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const listener = () => setNow(Date.now())
    const entry = ensureClock(intervalMs)
    entry.listeners.add(listener)
    // Ressincroniza no efeito (ex.: intervalMs mudou) em vez de esperar o
    // proximo tick do novo interval compartilhado.
    setNow(Date.now())
    return () => releaseClock(intervalMs, listener)
  }, [intervalMs])

  return now
}
