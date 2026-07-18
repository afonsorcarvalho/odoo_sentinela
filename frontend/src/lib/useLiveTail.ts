import { useEffect, useRef, useState } from 'react'
import { liveApi } from './api'
import type { LivePoint } from './types'

export function useLiveTail(code: string, max = 300) {
  const [tail, setTail] = useState<LivePoint[]>([])
  const maxRef = useRef(max)
  maxRef.current = max
  useEffect(() => {
    setTail([])
    const unsub = liveApi.subscribe(code, (p) => {
      setTail((prev) => {
        const next = [...prev, p]
        return next.length > maxRef.current ? next.slice(next.length - maxRef.current) : next
      })
    })
    return unsub
  }, [code])
  return { last: tail.length ? tail[tail.length - 1] : null, tail }
}
