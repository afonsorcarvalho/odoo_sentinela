import { useEffect, useRef, useState } from 'react'
import { Toast } from './Toast'
import type { AlarmEvent } from '../lib/types'

const AUTO_DISMISS_MS = 6000

export function ToastContainer({ alarms, loaded }: { alarms: AlarmEvent[]; loaded: boolean }) {
  const [visible, setVisible] = useState<AlarmEvent[]>([])
  const seenIds = useRef<Set<number> | null>(null)
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

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
    setVisible((prev) => [...novos, ...prev])
    novos.forEach((a) => {
      const timerId = setTimeout(() => dismiss(a.id), AUTO_DISMISS_MS)
      timers.current.set(a.id, timerId)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarms, loaded])

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
        <Toast key={a.id} alarm={a} onClose={() => dismiss(a.id)} />
      ))}
    </div>
  )
}
