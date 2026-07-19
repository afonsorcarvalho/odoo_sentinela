import { useEffect, useState } from 'react'

function reducedMotionQuery(): MediaQueryList {
  return window.matchMedia('(prefers-reduced-motion: reduce)')
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => reducedMotionQuery().matches)
  useEffect(() => {
    const mql = reducedMotionQuery()
    const onChange = () => setReduced(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return reduced
}

export function useSensorCarousel(count: number, intervalMs = 3000) {
  const [activeIndex, setActiveIndexState] = useState(0)
  const [paused, setPaused] = useState(false)
  const [resetTick, setResetTick] = useState(0)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    if (activeIndex >= count) setActiveIndexState(0)
  }, [count, activeIndex])

  useEffect(() => {
    if (count <= 1 || paused || reducedMotion) return
    const id = setInterval(() => {
      setActiveIndexState((i) => (i + 1) % count)
    }, intervalMs)
    return () => clearInterval(id)
  }, [count, paused, reducedMotion, intervalMs, resetTick])

  function setActiveIndex(index: number) {
    setActiveIndexState(index)
    setResetTick((t) => t + 1)
  }

  return {
    activeIndex,
    setActiveIndex,
    pause: () => setPaused(true),
    resume: () => setPaused(false),
  }
}
