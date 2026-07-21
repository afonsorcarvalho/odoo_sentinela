import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

export const VISIBLE_LIMIT = 8

// Duracao do flash de "novo" (ver AlarmItem/index.css: animacao de 5s). Usamos
// uma folga sobre os 5000ms para garantir que o timer nunca corta a
// animacao antes dela terminar (a keyframe usa `animation-fill-mode: both`,
// entao manter o item marcado por mais tempo que a animacao e seguro).
const NOVO_TTL_MS = 5300

export function AlarmPanel({
  alarms,
  areaNameByCode,
  onVerMais,
  filtro,
  mensagemVazio = 'Nenhum alarme ativo.',
}: {
  alarms: AlarmEvent[]
  areaNameByCode: Record<string, string>
  onVerMais?: () => void
  // Conteudo opcional (chips de filtro de area) renderizado logo abaixo do
  // header e acima da lista. Sem esta prop, o layout permanece identico ao
  // uso atual (ex.: DashboardPage), que nao passa filtro.
  filtro?: ReactNode
  // Mensagem do estado vazio. Default cobre "sem alarmes" (comportamento
  // atual). AlarmsWidget passa uma mensagem diferente para distinguir
  // "nenhuma area selecionada" (filtro zerado pelo operador) de "sem
  // alarme" (nada a reportar) -- sao estados semanticamente distintos.
  mensagemVazio?: string
}) {
  const ativos = alarms.filter((a) => a.status !== 'resolvido').length
  const visiveis = alarms.slice(0, VISIBLE_LIMIT)
  const restantes = alarms.length - VISIBLE_LIMIT

  const keyOf = (a: AlarmEvent) => `${a.sensor_code}-${a.timestamp_deteccao}`
  const currentKeysJoined = visiveis.map(keyOf).join('|')

  // "isNew" precisa ser sticky por NOVO_TTL_MS, nao recalculado a cada
  // render: o poll de useAlarms (5s) reexecuta este componente dentro da
  // propria janela do flash, e derivar isNew por diff-no-corpo-do-render
  // cortava a animacao no meio (classe some antes dos 5s completarem).
  // seenRef guarda as chaves ja vistas (semeado no primeiro efeito, sem
  // marcar nada como novo); timersRef guarda os timeouts pendentes para
  // poder cancela-los todos no unmount (o painel pode desmontar antes do
  // timer disparar, ex.: grid customizavel remontando o widget).
  const seenRef = useRef<Set<string> | null>(null)
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const [novos, setNovos] = useState<Set<string>>(new Set())

  useEffect(() => {
    const currentKeys = new Set(visiveis.map(keyOf))

    if (seenRef.current === null) {
      // Primeiro render: apenas semeia o "ja visto", nao anima a lista
      // inicial inteira.
      seenRef.current = currentKeys
      return
    }

    const chavesNovas = [...currentKeys].filter((k) => !seenRef.current!.has(k))
    seenRef.current = currentKeys
    if (chavesNovas.length === 0) return

    setNovos((prev) => {
      const next = new Set(prev)
      for (const k of chavesNovas) next.add(k)
      return next
    })

    for (const k of chavesNovas) {
      // Nao reagendar se ja ha um timer pendente para esta chave (evita
      // duplicar setTimeout em re-renders subsequentes com a mesma lista).
      if (timersRef.current.has(k)) continue
      const timer = setTimeout(() => {
        setNovos((prev) => {
          const next = new Set(prev)
          next.delete(k)
          return next
        })
        timersRef.current.delete(k)
      }, NOVO_TTL_MS)
      timersRef.current.set(k, timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentKeysJoined])

  // Cleanup no unmount: limpa qualquer timer ainda pendente.
  useEffect(() => {
    const timers = timersRef.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])

  return (
    <aside
      className="flex h-full w-full flex-col gap-3 rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${ativos > 0 ? 'var(--color-crit)' : 'var(--color-line)'}`,
      }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          Alarmes
        </h2>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-bold"
          style={{
            background: ativos > 0 ? 'var(--color-crit-soft)' : 'var(--color-good-soft)',
            color: ativos > 0 ? 'var(--color-crit)' : 'var(--color-good)',
          }}
        >
          {ativos}
        </span>
      </div>

      {filtro}

      {alarms.length === 0 ? (
        <p className="py-6 text-center text-sm" style={{ color: 'var(--color-muted)' }}>
          {mensagemVazio}
        </p>
      ) : (
        <>
          <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {visiveis.map((a) => (
              <AlarmItem
                key={a.id}
                alarm={a}
                areaName={areaNameByCode[a.area_code] ?? a.area_code}
                isNew={novos.has(keyOf(a))}
              />
            ))}
          </ul>
          {restantes > 0 && onVerMais && (
            <button
              type="button"
              onClick={onVerMais}
              className="min-h-11 w-full rounded-md text-sm font-semibold outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
              style={{ color: 'var(--color-primary)' }}
            >
              Ver mais ({restantes})
            </button>
          )}
        </>
      )}
    </aside>
  )
}
