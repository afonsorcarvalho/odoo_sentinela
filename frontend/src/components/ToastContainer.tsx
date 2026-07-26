import { useEffect, useRef, useState } from 'react'
import { Toast } from './Toast'
import { liveApi } from '../lib/api'
import type { AlarmEvent, AlarmTipoViolacao, LiveAlarme } from '../lib/types'

const AUTO_DISMISS_MS = 6000

// Normaliza epoch-ms (AlarmEvent.timestamp_deteccao) e ISO string
// (LiveAlarme.timestamp) pro mesmo resolucao de segundo, pra comparar as
// duas fontes na chave de reconciliacao abaixo.
function isoSegundo(ts: number | string): string {
  return new Date(ts).toISOString().slice(0, 19)
}

function chaveReconciliacao(sensor_code: string, ts: number | string): string {
  return `${sensor_code}|${isoSegundo(ts)}`
}

export function ToastContainer({
  alarms, areaNameByCode, loaded,
}: {
  alarms: AlarmEvent[]
  areaNameByCode: Record<string, string>
  loaded: boolean
}) {
  const [visible, setVisible] = useState<AlarmEvent[]>([])
  const seenIds = useRef<Set<number> | null>(null)
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  // Chaves `${sensor_code}|${isoSegundo(timestamp)}` ja toasteadas ao vivo:
  // usadas pelo efeito de poll abaixo pra suprimir o toast duravel do MESMO
  // alarme (o card + flash isNew no painel bastam nesse caso).
  const liveKeys = useRef<Set<string>>(new Set())
  // Ids efemeros pros toasts ao vivo (sem id no Odoo): contador decrescente
  // a partir de -1, nunca colide com ids reais (sempre positivos).
  const nextEphemeralId = useRef(-1)

  const clearTimer = (id: number) => {
    const t = timers.current.get(id)
    if (t !== undefined) {
      clearTimeout(t)
      timers.current.delete(id)
    }
  }

  const dismiss = (id: number) => {
    clearTimer(id)
    setVisible((prev) => prev.filter((v) => v.id !== id))
  }

  const mostrarToast = (a: AlarmEvent) => {
    setVisible((prev) => [a, ...prev])
    const timerId = setTimeout(() => dismiss(a.id), AUTO_DISMISS_MS)
    timers.current.set(a.id, timerId)
  }

  useEffect(() => {
    if (!loaded) {
      // Dados ainda carregando: nao estabelece baseline nem dispara toasts.
      return
    }
    if (seenIds.current === null) {
      // Primeira renderizacao com dados prontos: so estabelece a baseline,
      // nao dispara toast pra cada alarme ja existente ao abrir a tela.
      seenIds.current = new Set(alarms.map((a) => a.id))
      return
    }
    const novos = alarms.filter((a) => !seenIds.current!.has(a.id))
    if (novos.length === 0) return
    novos.forEach((a) => seenIds.current!.add(a.id))
    // Fallback: so toasta o duravel se NAO houve sinal ao vivo pro mesmo
    // alarme (mesma chave sensor+segundo) -- senao o card + flash isNew no
    // painel bastam, e toastar de novo duplicaria o aviso.
    novos
      .filter((a) => !liveKeys.current.has(chaveReconciliacao(a.sensor_code, a.timestamp_deteccao)))
      .forEach(mostrarToast)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarms, loaded])

  useEffect(() => {
    const unsub = liveApi.subscribeAlarme((a: LiveAlarme) => {
      liveKeys.current.add(chaveReconciliacao(a.sensor_code, a.timestamp))
      const id = nextEphemeralId.current--
      const sintetico: AlarmEvent = {
        id,
        sensor_code: a.sensor_code,
        area_code: a.area_code,
        timestamp_deteccao: Date.parse(a.timestamp),
        timestamp_resolucao_sensor: null,
        valor_lido: a.valor,
        tipo_violacao: a.tipo_violacao as AlarmTipoViolacao,
        limite_configurado_snapshot: a.valor,
        status: a.tipo_evento === 'saida_alarme' ? 'resolvido' : 'aberto',
        usuario_responsavel: null,
        data_resolucao: null,
        observacoes: null,
      }
      mostrarToast(sintetico)
    })
    return unsub
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timersMap = timers.current
    return () => {
      timersMap.forEach((t) => clearTimeout(t))
      timersMap.clear()
    }
  }, [])

  if (visible.length === 0) return null

  return (
    <div className="fixed right-6 top-[70px] z-20 flex flex-col gap-2.5" aria-live="polite">
      {visible.map((a) => (
        <Toast key={a.id} alarm={a} areaName={areaNameByCode[a.area_code] ?? a.area_code} onClose={() => dismiss(a.id)} />
      ))}
    </div>
  )
}
