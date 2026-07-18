import { useEffect, useRef, useState } from 'react'
import { Toast } from './Toast'
import type { AlarmEvent } from '../lib/types'

const AUTO_DISMISS_MS = 6000

export function ToastContainer({ alarms }: { alarms: AlarmEvent[] }) {
  const [visible, setVisible] = useState<AlarmEvent[]>([])
  const seenIds = useRef<Set<number> | null>(null)

  useEffect(() => {
    if (seenIds.current === null) {
      // Primeira renderizacao: so estabelece a baseline, nao dispara toast
      // pra cada alarme ja existente ao abrir a tela.
      seenIds.current = new Set(alarms.map((a) => a.id))
      return
    }
    const novos = alarms.filter((a) => !seenIds.current!.has(a.id))
    if (novos.length === 0) return
    novos.forEach((a) => seenIds.current!.add(a.id))
    setVisible((prev) => [...novos, ...prev])
    novos.forEach((a) => {
      setTimeout(() => setVisible((prev) => prev.filter((v) => v.id !== a.id)), AUTO_DISMISS_MS)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarms])

  if (visible.length === 0) return null

  return (
    <div className="fixed right-6 top-[70px] z-20 flex flex-col gap-2.5" aria-live="polite">
      {visible.map((a) => (
        <Toast key={a.id} alarm={a} onClose={() => setVisible((prev) => prev.filter((v) => v.id !== a.id))} />
      ))}
    </div>
  )
}
