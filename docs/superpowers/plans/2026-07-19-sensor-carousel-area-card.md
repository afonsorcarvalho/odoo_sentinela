# Sensor Carousel no AreaCard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `AreaCard` mostra 1 sensor por vez (valor grande, destacado), alternando automaticamente entre os sensores da área a cada 3s, com pausa on-hover e dots de navegação manual.

**Architecture:** Novo hook `useSensorCarousel` (estado de índice ativo + timer + reduced-motion) isolado em `src/lib/useSensorCarousel.ts`, consumido por `AreaCard.tsx`. Nenhuma dependência nova — `setInterval` + Tailwind, seguindo o padrão já usado no projeto (`useLiveTail.ts`).

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library (fake timers), Tailwind 4.

## Global Constraints

- Intervalo de rotação fixo em **3000ms** nesta fase (configurável via Odoo é trabalho futuro, fora de escopo — não implementar toggle/prop para isso).
- Sem dependência nova (sem embla, swiper, framer-motion). Só `setInterval` + CSS Tailwind.
- Área com **1 sensor**: sem carrossel, sem dots, sensor sempre visível.
- Dots usam `role="tab"` (não `role="button"` implícito de `<button>` sem role) — `DashboardPage.test.tsx:91` faz `within(preparoCard).getAllByRole('button')` esperando pegar o botão de valor do sensor ativo como primeiro (e único) botão do card; dots com `role="tab"` não entram nessa query e não podem quebrar esse teste.
- Cor do valor em destaque segue `alarm_state` via `statusTextColor()` já existente em `statusVisuals.tsx` — mesma regra do valor pequeno de hoje (`ok`/`unknown` → `var(--color-ink)`, senão `statusTextColor(state)`).
- `prefers-reduced-motion: reduce` desativa o auto-avanço (dots continuam clicáveis manualmente).
- Clique no valor ativo continua chamando `onSelectSensor(sensor_code)` — API pública do componente (`AreaCard` props) não muda.
- jsdom não implementa `window.matchMedia` — é a primeira vez que o projeto usa isso; precisa de mock global em `src/test/setup.ts` (default `matches: false`) para não quebrar toda a suite que renderiza `AreaCard`/`DashboardPage`.

---

### Task 1: Hook `useSensorCarousel` + `usePrefersReducedMotion`

**Files:**
- Create: `frontend/src/lib/useSensorCarousel.ts`
- Create: `frontend/src/lib/useSensorCarousel.test.ts`
- Modify: `frontend/src/test/setup.ts`

**Interfaces:**
- Produces: `usePrefersReducedMotion(): boolean`
- Produces: `useSensorCarousel(count: number, intervalMs?: number): { activeIndex: number; setActiveIndex: (index: number) => void; pause: () => void; resume: () => void }`
  - `activeIndex` começa em `0`, avança `(i+1) % count` a cada `intervalMs` enquanto `count > 1`, não pausado e sem reduced-motion.
  - `setActiveIndex(index)` troca o índice imediatamente e reinicia o ciclo do timer a partir dali.
  - `pause()` / `resume()` param/retomam o auto-avanço; `resume()` reinicia a contagem de `intervalMs` do zero (não continua de onde parou).

- [ ] **Step 1: Adicionar mock global de `matchMedia` em `src/test/setup.ts`**

Ler o arquivo atual primeiro (já existe, só tem o import do jest-dom). Novo conteúdo completo:

```ts
import '@testing-library/jest-dom'

// jsdom nao implementa matchMedia; usePrefersReducedMotion (useSensorCarousel.ts)
// e o primeiro uso no projeto. Default matches:false (sem reducao de movimento);
// testes especificos de reduced-motion sobrescrevem via vi.stubGlobal.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
```

- [ ] **Step 2: Escrever o teste falho do hook**

Criar `frontend/src/lib/useSensorCarousel.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSensorCarousel } from './useSensorCarousel'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useSensorCarousel', () => {
  it('nao avanca sozinho quando count <= 1', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(1))
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('avanca activeIndex a cada intervalMs, ciclando', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(1)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('pause() para o avanco; resume() reinicia o ciclo do zero', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(2, 3000))
    act(() => {
      result.current.pause()
    })
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      result.current.resume()
    })
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(result.current.activeIndex).toBe(0)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.activeIndex).toBe(1)
  })

  it('setActiveIndex troca na hora e reinicia o timer de 3s', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    act(() => {
      result.current.setActiveIndex(2)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current.activeIndex).toBe(2)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(result.current.activeIndex).toBe(0)
  })

  it('prefers-reduced-motion: reduce -> nao avanca sozinho', () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    const { result } = renderHook(() => useSensorCarousel(3, 3000))
    act(() => {
      vi.advanceTimersByTime(9000)
    })
    expect(result.current.activeIndex).toBe(0)
  })
})
```

- [ ] **Step 3: Rodar teste, confirmar que falha (módulo não existe)**

Run: `cd frontend && npx vitest run src/lib/useSensorCarousel.test.ts`
Expected: FAIL — `Cannot find module './useSensorCarousel'` (ou erro de import).

- [ ] **Step 4: Implementar o hook**

Criar `frontend/src/lib/useSensorCarousel.ts`:

```ts
import { useEffect, useState } from 'react'

function reducedMotionQuery(): MediaQueryList {
  return window.matchMedia('(prefers-reduced-motion: reduce)')
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => reducedMotionQuery().matches)
  useEffect(() => {
    const mql = reducedMotionQuery()
    const onChange = () => setReduced(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return reduced
}

export function useSensorCarousel(count: number, intervalMs = 3000) {
  const [activeIndex, setActiveIndexState] = useState(0)
  const [paused, setPaused] = useState(false)
  const [resetTick, setResetTick] = useState(0)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    if (activeIndex >= count) setActiveIndexState(0)
  }, [count, activeIndex])

  useEffect(() => {
    if (count <= 1 || paused || reducedMotion) return
    const id = setInterval(() => {
      setActiveIndexState((i) => (i + 1) % count)
    }, intervalMs)
    return () => clearInterval(id)
  }, [count, paused, reducedMotion, intervalMs, resetTick])

  function setActiveIndex(index: number) {
    setActiveIndexState(index)
    setResetTick((t) => t + 1)
  }

  return {
    activeIndex,
    setActiveIndex,
    pause: () => setPaused(true),
    resume: () => setPaused(false),
  }
}
```

- [ ] **Step 5: Rodar teste, confirmar que passa**

Run: `cd frontend && npx vitest run src/lib/useSensorCarousel.test.ts`
Expected: PASS (5 testes).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/useSensorCarousel.ts frontend/src/lib/useSensorCarousel.test.ts frontend/src/test/setup.ts
git commit -m "feat: hook useSensorCarousel com pausa e reduced-motion"
```

---

### Task 2: `AreaCard` usa o carrossel — valor grande, dots, pausa on-hover

**Files:**
- Modify: `frontend/src/components/AreaCard.tsx`
- Modify: `frontend/src/components/AreaCard.test.tsx`

**Interfaces:**
- Consumes: `useSensorCarousel(count: number, intervalMs?: number)` de `../lib/useSensorCarousel` (Task 1).
- Consumes: `statusTextColor(state): string` de `./statusVisuals` (já existe).
- Produces: nenhuma interface pública nova — props de `AreaCard` não mudam (`group`, `thresholdsByCode`, `liveByCode`, `selectedSensorCode`, `onSelectSensor`, `hadAlarmToday`).

- [ ] **Step 1: Atualizar `AreaCard.test.tsx` com os novos casos (TDD — vai falhar antes do Step 3)**

Substituir o conteúdo completo de `frontend/src/components/AreaCard.test.tsx`:

```tsx
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { AreaCard } from './AreaCard'
import { statusTextColor } from './statusVisuals'
import type { AreaGroup } from '../lib/aggregateStatus'

afterEach(() => vi.useRealTimers())

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}
const singleGroup: AreaGroup = {
  area: { area_code: 'SALA1', name: 'Sala 1', category: 'Sala' },
  sensors: [group.sensors[0]],
}
const thresholdsByCode = {
  'TEMP-EXP-01': { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false },
  'PRESS-EXP-01': { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true },
}
const liveByCode = {
  'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' as const },
  'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: 1, value: -3.6, alarm_state: 'ok' as const },
}

describe('AreaCard', () => {
  it('mostra nome da area e o sensor ativo (1o da lista) com valor mono', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/21\.0/)).toBeInTheDocument()
  })

  it('clicar no valor do sensor ativo chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })

  it('area com 1 sensor nao mostra dots', () => {
    render(
      <AreaCard group={singleGroup} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('area com N sensores mostra 1 dot por sensor', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)
  })

  it('avanca automaticamente entre sensores a cada 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    expect(screen.queryByText('Temperatura')).not.toBeInTheDocument()
  })

  it('hover pausa avanco automatico; mouse leave retoma o ciclo do zero', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const card = screen.getByTestId('area-card-EXPURGO')
    fireEvent.mouseEnter(card)
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()

    fireEvent.mouseLeave(card)
    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
  })

  it('clicar no dot pula pro sensor certo e reinicia o ciclo de 3s', () => {
    vi.useFakeTimers()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const dots = screen.getAllByRole('tab')
    fireEvent.click(dots[1])
    expect(screen.getByText('Pressão')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2999)
    })
    expect(screen.getByText('Pressão')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
  })

  it('cor do valor em destaque reflete alarm_state (crit)', () => {
    const critLive = {
      ...liveByCode,
      'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 30, alarm_state: 'crit' as const },
    }
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={critLive}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    const value = screen.getByText(/30\.0/)
    expect(value.style.color).toBe(statusTextColor('crit'))
  })
})
```

- [ ] **Step 2: Rodar os testes, confirmar que os novos falham**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: FAIL nos casos novos (sem `role="tab"`, sem avanço automático, valor não é `text-3xl` — o componente ainda não mudou).

- [ ] **Step 3: Reescrever `AreaCard.tsx`**

Substituir o conteúdo completo de `frontend/src/components/AreaCard.tsx`:

```tsx
import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { useSensorCarousel } from '../lib/useSensorCarousel'
import { StatusChip } from './StatusChip'
import { StatusDot } from './StatusDot'
import { statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

const BORDER_COLOR: Record<ReturnType<typeof worstAlarmState>, string> = {
  ok: 'var(--color-line)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-line)',
}

const CAROUSEL_INTERVAL_MS = 3000

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)
  const carousel = useSensorCarousel(group.sensors.length, CAROUSEL_INTERVAL_MS)
  const activeSensor = group.sensors[carousel.activeIndex] ?? group.sensors[0]
  const activeState = sensorDisplayState(
    thresholdsByCode[activeSensor.sensor_code] ?? null,
    liveByCode[activeSensor.sensor_code],
  )
  const activeLive = liveByCode[activeSensor.sensor_code]
  const activeSelected = activeSensor.sensor_code === selectedSensorCode

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${BORDER_COLOR[aggregate]}`,
      }}
      data-testid={`area-card-${group.area.area_code}`}
      onMouseEnter={carousel.pause}
      onMouseLeave={carousel.resume}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          {group.area.name}
        </h2>
        <div className="flex items-center gap-2">
          {hadAlarmToday && (
            <span
              aria-label="Houve não conformidade hoje"
              className="flex size-[18px] items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-warn-soft)', color: 'var(--color-warn)' }}
            >
              !
            </span>
          )}
          <StatusChip state={aggregate} />
        </div>
      </div>

      <div className="mt-3 border-t" style={{ borderColor: 'var(--color-line)' }} />

      <div className="mt-2">
        <button
          type="button"
          onClick={() => onSelectSensor(activeSensor.sensor_code)}
          className="flex w-full flex-col items-start gap-1 rounded-md px-2 py-2 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
          style={{ background: activeSelected ? 'var(--color-panel)' : 'transparent' }}
        >
          <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            <StatusDot state={activeState} />
            {activeSensor.measurement_type.name}
          </span>
          <span
            className="font-mono text-3xl font-bold tabular-nums"
            style={{
              color: activeState === 'ok' || activeState === 'unknown' ? 'var(--color-ink)' : statusTextColor(activeState),
            }}
          >
            {activeLive ? activeLive.value.toFixed(1) : '—'}{' '}
            <span className="text-base font-medium">{activeSensor.unidade}</span>
          </span>
        </button>

        {group.sensors.length > 1 && (
          <div className="mt-2 flex items-center justify-center gap-1.5" role="tablist" aria-label="Sensores da área">
            {group.sensors.map((s, i) => (
              <button
                key={s.sensor_code}
                type="button"
                role="tab"
                aria-selected={i === carousel.activeIndex}
                aria-label={s.measurement_type.name}
                onClick={() => carousel.setActiveIndex(i)}
                className="size-1.5 rounded-full transition-colors duration-200 ease-out motion-reduce:transition-none"
                style={{ background: i === carousel.activeIndex ? 'var(--color-ink)' : 'var(--color-line)' }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rodar os testes do componente, confirmar que passam**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: PASS (9 testes).

- [ ] **Step 5: Rodar a suite inteira do frontend + typecheck, confirmar que nada quebrou**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: PASS em todos os arquivos, incluindo `src/pages/DashboardPage.test.tsx` (o teste que faz `within(preparoCard).getAllByRole('button')` deve continuar pegando só o botão de valor — dots são `role="tab"`). Nenhum erro de tipo.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx
git commit -m "feat(frontend): AreaCard rotaciona sensores em carrossel com valor em destaque"
```
