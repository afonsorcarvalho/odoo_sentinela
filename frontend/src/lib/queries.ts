import { useQuery, useQueries } from '@tanstack/react-query'
import { metaApi, historyApi, alarmApi, configApi } from './api'
import type { Window } from './types'

export function useSensorMeta(code: string) {
  return useQuery({ queryKey: ['sensor', code], queryFn: () => metaApi.getSensor(code) })
}
export function useThreshold(code: string) {
  return useQuery({ queryKey: ['threshold', code], queryFn: () => metaApi.getThreshold(code) })
}
export function useHistory(code: string, window: Window) {
  return useQuery({ queryKey: ['history', code, window], queryFn: () => historyApi.getHistory(code, window), enabled: code !== '' })
}

export function useSensors() {
  return useQuery({ queryKey: ['sensors'], queryFn: () => metaApi.listSensors() })
}

// Mesma queryKey de useThreshold (['threshold', code]) — cache compartilhado:
// se um sensor ja foi visto no Detalhe do Sensor, a Overview reusa o cache.
export function useThresholds(codes: string[]) {
  return useQueries({
    queries: codes.map((code) => ({
      queryKey: ['threshold', code],
      queryFn: () => metaApi.getThreshold(code),
    })),
  })
}

export function useAlarms() {
  return useQuery({ queryKey: ['alarms'], queryFn: () => alarmApi.listAlarms(), refetchInterval: 5000 })
}

export function useConfig() {
  return useQuery({ queryKey: ['config'], queryFn: () => configApi.getConfig(), staleTime: 5 * 60 * 1000 })
}
