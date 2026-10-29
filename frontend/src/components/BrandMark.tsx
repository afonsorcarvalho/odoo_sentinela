import { useId } from 'react'

const ESCUDO = 'M32 4 L54 12 V30 C54 44 44.5 54.5 32 60 C19.5 54.5 10 44 10 30 V12 Z'

// Símbolo Sentinela (branding/sentinela-simbolo.svg): escudo com contorno e
// onda de pulso vazada — o recorte mostra o fundo, então serve nos dois temas.
export function BrandMark({ size = 34 }: { size?: number }) {
  const mascara = useId()
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ color: 'var(--color-primary)' }}>
      <path d={ESCUDO} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <g transform="translate(32 32) scale(0.87) translate(-32 -32)">
        <mask id={mascara}>
          <rect width="64" height="64" fill="#fff" />
          <path d="M16 33 H24 L28 24 L33 42 L37 30 L40 33 H48" fill="none" stroke="#000" strokeWidth="4.5"
            strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="48" cy="33" r="3.6" fill="#000" />
        </mask>
        <path d={ESCUDO} fill="currentColor" mask={`url(#${mascara})`} />
      </g>
    </svg>
  )
}
