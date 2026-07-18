import { useEffect, useState } from 'react'
import { resolveOklchColor } from './oklch'

function resolve(varName: string): string {
  if (typeof window === 'undefined') return ''
  const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
  return resolveOklchColor(raw)
}

// Le o valor resolvido (sRGB) de uma custom property no :root e reage a
// trocas de tema. ECharts pinta em <canvas> e nao entende `var(--...)`, entao
// qualquer cor de tema que alimente o chart precisa passar por aqui primeiro.
// Observa mudancas de classe em <html> (é assim que o ThemeToggle liga/desliga
// `.dark`) para re-resolver quando o tema muda.
export function useThemeColor(varName: string): string {
  const [color, setColor] = useState(() => resolve(varName))

  useEffect(() => {
    setColor(resolve(varName))
    const observer = new MutationObserver(() => setColor(resolve(varName)))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [varName])

  return color
}
