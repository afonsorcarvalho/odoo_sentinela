import { useEffect, useState } from 'react'
import { liveApi } from './api'
import type { LiveConnectionState } from './types'

// Analogo a useLiveTail/useLiveStatuses: inscreve no mount, limpa no unmount.
// Otimista no estado inicial (ver design doc A3) -- liveApi.subscribeConnection
// ja emite o estado atual sincronamente na inscricao, entao 'live' aqui e so
// o valor antes do primeiro efeito rodar.
export function useLiveConnection(): LiveConnectionState {
  const [state, setState] = useState<LiveConnectionState>('live')

  useEffect(() => {
    return liveApi.subscribeConnection(setState)
  }, [])

  return state
}
