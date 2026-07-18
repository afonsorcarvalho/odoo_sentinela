import { useEffect, useState } from 'react'
import { liveApi } from './api'
import type { LivePoint } from './types'

// Analogo a useLiveTail, mas sem buffer: guarda so o ULTIMO LivePoint por
// sensor_code (Overview so precisa do estado atual de cada sensor, nao do
// historico da cauda).
//
// `codes.join(',')` como chave do efeito (nao `codes` direto): o array chega
// recriado a cada render do chamador (ex.: `sensors.map(s => s.sensor_code)`),
// e usar a referencia direta re-assinaria (e zeraria o estado) a cada render.
// Seguro para o formato de sensor_code deste projeto (sem virgula).
export function useLiveStatuses(codes: string[]): Record<string, LivePoint> {
  const [byCode, setByCode] = useState<Record<string, LivePoint>>({})
  const codesKey = codes.join(',')

  useEffect(() => {
    setByCode({})
    const unsubs = codes.map((code) =>
      liveApi.subscribe(code, (p) => {
        setByCode((prev) => ({ ...prev, [code]: p }))
      }),
    )
    return () => unsubs.forEach((unsub) => unsub())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codesKey])

  return byCode
}
