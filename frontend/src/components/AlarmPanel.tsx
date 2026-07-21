import { useEffect, useRef, type ReactNode } from 'react'
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

export const VISIBLE_LIMIT = 8

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
  const seenRef = useRef<Set<string> | null>(null)
  const currentKeys = new Set(visiveis.map(keyOf))
  // Primeiro render: nada é "novo" (não animar a lista inicial inteira).
  const novos = seenRef.current === null
    ? new Set<string>()
    : new Set([...currentKeys].filter((k) => !seenRef.current!.has(k)))
  useEffect(() => {
    seenRef.current = currentKeys
  })

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
                key={keyOf(a)}
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
