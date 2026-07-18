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
    return () => { window.removeEventListener('resize', onResize); chart.current?.dispose(); chart.current = null }
  }, [])
  return { el, chart }
}
