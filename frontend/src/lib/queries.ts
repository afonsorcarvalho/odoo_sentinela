import { useQuery } from '@tanstack/react-query'
import { metaApi, historyApi } from './api'
import type { Window } from './types'

export function useSensorMeta(code: string) {
  return useQuery({ queryKey: ['sensor', code], queryFn: () => metaApi.getSensor(code) })
}
export function useThreshold(code: string) {
  return useQuery({ queryKey: ['threshold', code], queryFn: () => metaApi.getThreshold(code) })
}
export function useHistory(code: string, window: Window) {
  return useQuery({ queryKey: ['history', code, window], queryFn: () => historyApi.getHistory(code, window) })
}
