import { useEffect, useRef, useState } from 'react'
import { usePrefersReducedMotion } from './useSensorCarousel'

// Anima um número do valor anterior até o alvo via requestAnimationFrame,
// easing cubic-out. Usado no KpiWidget para o "count-up" ao chegar novo valor
// ao vivo. Sob prefers-reduced-motion, retorna o alvo imediatamente.
// null passa direto (KPI sem leitura ainda).
export function useCountUp(target: number | null, opts?: { durationMs?: number }): number | null {
  const durationMs = opts?.durationMs ?? 550
  const reduced = usePrefersReducedMotion()
  const [display, setDisplay] = useState<number | null>(target)
  const fromRef = useRef<number | null>(target)
  const lastValueRef = useRef<number | null>(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === null) {
      setDisplay(null)
      fromRef.current = null
      lastValueRef.current = null
      return
    }
    if (reduced || fromRef.current === null) {
      setDisplay(target)
      fromRef.current = target
      lastValueRef.current = target
      return
    }
    const from = fromRef.current
    const to = target
    if (from === to) return
    const t0 = performance.now()
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / durationMs)
      const eased = 1 - Math.pow(1 - k, 3)
      const value = from + (to - from) * eased
      setDisplay(value)
      lastValueRef.current = value
      if (k < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        setDisplay(to)
        lastValueRef.current = to
        fromRef.current = to
      }
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      // Ao interromper, ancora o próximo "from" no último valor exibido de fato
      // (não no alvo desta animação, que pode nunca ter sido mostrado).
      fromRef.current = lastValueRef.current
    }
  }, [target, reduced, durationMs])

  return display
}
