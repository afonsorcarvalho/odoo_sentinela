import { useCallback, useRef } from 'react'

// Escala um texto para preencher o container em LARGURA e ALTURA, mantendo-o
// numa linha. Mede o tamanho natural do texto a um font-size de referência
// (100px) e aplica um font-size proporcional ao menor dos dois fatores
// (largura/altura) — o que garante caber nos dois eixos sem estourar.
//
// Loop-free: mudar o font-size do texto NÃO altera o tamanho da caixa (que tem
// tamanho definido pelo layout do card / célula do grid), então o
// ResizeObserver observando a caixa não re-dispara por causa do próprio
// ajuste. tabular-nums no texto faz a largura depender só da contagem de
// caracteres, então refazer o fit só quando o conteúdo muda de comprimento
// (não a cada frame do count-up) é suficiente.
//
// `boxRef` é um CALLBACK ref: reconecta o ResizeObserver quando o nó da caixa
// muda. Isso é necessário porque a caixa pode remontar (ex.: no AreaCard ela
// fica dentro do wrapper com key=sensor_code, que remonta a cada troca do
// carrossel) — um ref-objeto fixo deixaria o observer preso no nó antigo.
//
// `fillRatio` (<1) deixa uma folga proporcional em todos os lados ("respiro").
export function useFitText(opts?: { min?: number; max?: number; fillRatio?: number }) {
  const textRef = useRef<HTMLElement>(null)
  const boxElRef = useRef<HTMLElement | null>(null)
  const roRef = useRef<ResizeObserver | null>(null)
  const min = opts?.min ?? 12
  const max = opts?.max ?? 160
  const fillRatio = opts?.fillRatio ?? 0.88

  const fit = useCallback(() => {
    const box = boxElRef.current
    const text = textRef.current
    if (!box || !text) return
    const cw = box.clientWidth
    const ch = box.clientHeight
    // jsdom (testes) e caixas ainda não medidas reportam 0 — nada a fazer.
    if (cw === 0 || ch === 0) return
    // Mede o tamanho natural a 100px. O valor intermediário nunca pinta
    // (mesmo tick síncrono), mas força um reflow ao ler scrollWidth/Height.
    text.style.fontSize = '100px'
    const tw = text.scrollWidth
    const th = text.scrollHeight
    if (tw === 0 || th === 0) return
    const size = Math.min((cw / tw) * 100, (ch / th) * 100) * fillRatio
    text.style.fontSize = `${Math.max(min, Math.min(max, size))}px`
  }, [min, max, fillRatio])

  // Callback ref na caixa: (re)conecta o observer ao nó atual e refaz o fit.
  const boxRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (roRef.current) {
        roRef.current.disconnect()
        roRef.current = null
      }
      boxElRef.current = node
      if (node) {
        const ro = new ResizeObserver(() => fit())
        ro.observe(node)
        roRef.current = ro
        fit()
      }
    },
    [fit],
  )

  return { boxRef, textRef, fit }
}
