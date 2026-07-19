import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export function useECharts() {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current)
    const onResize = () => chart.current?.resize()
    window.addEventListener('resize', onResize)
    // Resize da janela nao cobre o caso do card mudar de tamanho sozinho
    // (drag/resize do react-grid-layout, ou mudanca de layout do dashboard) —
    // sem isso o canvas do ECharts fica com o tamanho antigo (cortado/com
    // espaco em branco) ate a proxima resize da window. ResizeObserver
    // acompanha o elemento em si.
    const ro = new ResizeObserver(onResize)
    ro.observe(el.current)
    return () => {
      window.removeEventListener('resize', onResize)
      ro.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])
  return { el, chart }
}
