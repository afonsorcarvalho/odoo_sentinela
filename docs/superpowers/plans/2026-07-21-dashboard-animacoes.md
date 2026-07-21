# Animações da dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar micro-interações de polish (nível "equilibrado") em 8 superfícies da dashboard Sentinela, tudo em CSS/Tailwind + hooks, sem dependência de animação nova.

**Architecture:** Tokens de motion centralizados no bloco `@theme` de `index.css`; keyframes globais reutilizáveis no mesmo arquivo; um hook `useCountUp` (rAF) para o KPI; componentes ganham classes/estilos de transição. Cada efeito degrada para instantâneo sob `prefers-reduced-motion`, reusando o hook `usePrefersReducedMotion` já existente em `src/lib/useSensorCarousel.ts`.

**Tech Stack:** React 19, TypeScript, Tailwind v4 (`@theme`), Vitest + Testing Library, react-grid-layout, @floating-ui/react. Comando de teste: `npm test` (= `vitest run`) rodado de `frontend/`.

## Global Constraints

- **Sem dependência nova.** Proibido adicionar framer-motion/`motion` ou qualquer lib de animação. Só CSS, Tailwind e hooks próprios.
- **`prefers-reduced-motion` sempre respeitado.** Todo efeito com `transform`/keyframe/`transition` de movimento deve degradar para instantâneo. Usar a variante Tailwind `motion-reduce:` (`motion-reduce:transition-none`, `motion-reduce:animate-none`) e/ou o hook `usePrefersReducedMotion` (exportado de `src/lib/useSensorCarousel.ts`).
- **Tokens de motion.** Durações/easings vêm SEMPRE dos tokens do `@theme` (Task 1). Nunca hardcodar `cubic-bezier`/`ms` novos em componente sem passar por token, salvo delays de stagger calculados em JS.
- **Testes existentes verdes.** As mudanças são aditivas; nenhum teste atual (367+) pode quebrar. Rodar `npm test` ao fim de cada task.
- **Todos os comandos rodam de `frontend/`.**

---

### Task 1: Tokens de motion + keyframes globais

Fundação: tokens de duração/easing no `@theme` e keyframes reutilizáveis. Sem esses, as tasks seguintes não têm o vocabulário compartilhado.

**Files:**
- Modify: `frontend/src/index.css` (bloco `@theme`, linhas ~5-37; e fim do arquivo p/ keyframes)

**Interfaces:**
- Produces (CSS custom properties, disponíveis em claro e `.theme-control`):
  - `--ease-out-soft: cubic-bezier(.22,.61,.36,1)`
  - `--ease-in-soft: cubic-bezier(.55,.06,.68,.19)`
  - `--ease-overshoot: cubic-bezier(.34,1.5,.64,1)`
  - `--dur-fast: 180ms` · `--dur-base: 300ms` · `--dur-slow: 400ms`
- Produces (keyframes globais): `@keyframes widget-in`, `@keyframes carousel-in`, `@keyframes alarm-in`, `@keyframes kpi-bump`, `@keyframes editor-wobble`.

- [ ] **Step 1: Adicionar tokens de motion ao `@theme`**

No bloco `@theme` de `frontend/src/index.css`, logo antes de `--font-mono` (linha ~35), adicionar:

```css
  /* ---------- Motion (polish "equilibrado") ---------- */
  /* Durações/easings centralizados: um só ponto de ajuste. Não dependem de
     cor, então valem igual no tema claro e no .theme-control. */
  --ease-out-soft:  cubic-bezier(.22, .61, .36, 1);
  --ease-in-soft:   cubic-bezier(.55, .06, .68, .19);
  --ease-overshoot: cubic-bezier(.34, 1.5, .64, 1);
  --dur-fast: 180ms;
  --dur-base: 300ms;
  --dur-slow: 400ms;
```

- [ ] **Step 2: Adicionar keyframes globais ao fim do arquivo**

No fim de `frontend/src/index.css`, adicionar:

```css
/* ---------- Keyframes de motion (ver docs/superpowers/specs/2026-07-21-dashboard-animacoes-design.md) ----------
   Todos os usos aplicam estes via classes que já trazem guarda de
   prefers-reduced-motion (motion-reduce:animate-none) no componente. */
@keyframes widget-in {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes carousel-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes alarm-in {
  from { opacity: 0; transform: translateY(-12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes kpi-bump {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.12); }
  100% { transform: scale(1); }
}
@keyframes editor-wobble {
  0%, 100% { transform: rotate(-0.4deg); }
  50%      { transform: rotate(0.4deg); }
}
```

- [ ] **Step 3: Verificar build de CSS (Tailwind aceita tokens)**

Run: `npm run build`
Expected: build conclui sem erro (tsc + vite). Os tokens em `@theme` são válidos; keyframes globais são CSS puro.

- [ ] **Step 4: Rodar testes (regressão)**

Run: `npm test`
Expected: PASS (suite atual intacta — mudança é só CSS).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(dashboard): tokens de motion + keyframes globais"
```

---

### Task 2: Hook `useCountUp` + count-up/bump no KPI

O KPI anima do valor anterior ao novo (rAF) com um bump. É a única lógica de animação com teste unitário real.

**Files:**
- Create: `frontend/src/lib/useCountUp.ts`
- Create: `frontend/src/lib/useCountUp.test.ts`
- Modify: `frontend/src/components/widgets/KpiWidget.tsx`

**Interfaces:**
- Produces: `useCountUp(target: number | null, opts?: { durationMs?: number }): number | null` — retorna o valor interpolado a cada frame; quando `target` muda, anima de valor atual→target em `durationMs` (default 550) com easing cubic-out. Se `prefers-reduced-motion`, retorna `target` direto (sem animar). `null` passa direto como `null`.

- [ ] **Step 1: Escrever teste falho do hook**

Create `frontend/src/lib/useCountUp.test.ts`:

```ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCountUp } from './useCountUp'

// rAF determinístico via fake timers: cada "frame" avança performance.now.
function installRaf() {
  let now = 0
  vi.spyOn(performance, 'now').mockImplementation(() => now)
  vi.stubGlobal(
    'requestAnimationFrame',
    (cb: FrameRequestCallback) => setTimeout(() => { now += 16; cb(now) }, 16) as unknown as number,
  )
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
}

describe('useCountUp', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('interpola do valor anterior ate o alvo', () => {
    vi.useFakeTimers()
    installRaf()
    const { result, rerender } = renderHook(({ v }) => useCountUp(v, { durationMs: 100 }), {
      initialProps: { v: 0 as number | null },
    })
    expect(result.current).toBe(0)
    rerender({ v: 10 })
    act(() => { vi.advanceTimersByTime(50) })
    expect(result.current).toBeGreaterThan(0)
    expect(result.current).toBeLessThan(10)
    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe(10)
    vi.useRealTimers()
  })

  it('prefers-reduced-motion: retorna o alvo direto sem animar', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    const { result, rerender } = renderHook(({ v }) => useCountUp(v), {
      initialProps: { v: 0 as number | null },
    })
    rerender({ v: 42 })
    expect(result.current).toBe(42)
  })

  it('propaga null', () => {
    const { result } = renderHook(() => useCountUp(null))
    expect(result.current).toBeNull()
  })
})
```

- [ ] **Step 2: Rodar teste p/ ver falhar**

Run: `npm test -- useCountUp`
Expected: FAIL ("Cannot find module './useCountUp'").

- [ ] **Step 3: Implementar o hook**

Create `frontend/src/lib/useCountUp.ts`:

```ts
import { useEffect, useRef, useState } from 'react'
import { usePrefersReducedMotion } from './useSensorCarousel'

// Anima um número do valor anterior até o alvo via requestAnimationFrame,
// easing cubic-out. Usado no KpiWidget para o "count-up" ao chegar novo valor
// ao vivo. Sob prefers-reduced-motion, retorna o alvo imediatamente.
// null passa direto (KPI sem leitura ainda).
export function useCountUp(target: number | null, opts?: { durationMs?: number }): number | null {
  const durationMs = opts?.durationMs ?? 550
  const reduced = usePrefersReducedMotion()
  const [display, setDisplay] = useState<number | null>(target)
  const fromRef = useRef<number | null>(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === null) {
      setDisplay(null)
      fromRef.current = null
      return
    }
    if (reduced || fromRef.current === null) {
      setDisplay(target)
      fromRef.current = target
      return
    }
    const from = fromRef.current
    const to = target
    if (from === to) return
    const t0 = performance.now()
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / durationMs)
      const eased = 1 - Math.pow(1 - k, 3)
      const value = from + (to - from) * eased
      setDisplay(value)
      if (k < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        setDisplay(to)
        fromRef.current = to
      }
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      // Ao interromper, ancora o próximo "from" no último valor mostrado.
      fromRef.current = to
    }
  }, [target, reduced, durationMs])

  return display
}
```

- [ ] **Step 4: Rodar teste p/ passar**

Run: `npm test -- useCountUp`
Expected: PASS (3 testes).

- [ ] **Step 5: Ligar count-up + bump no KpiWidget**

Em `frontend/src/components/widgets/KpiWidget.tsx`:

Adicionar import no topo:
```ts
import { useCountUp } from '../../lib/useCountUp'
```

Dentro do componente, após a linha `const cor = state === 'ok' ...`, calcular o valor exibido animado e o número de casas decimais do valor bruto (preservar formatação):
```ts
  const rawValue = last?.value ?? null
  const animated = useCountUp(rawValue)
  // Preserva as casas decimais do valor bruto durante a interpolação.
  const casas = rawValue != null && !Number.isInteger(rawValue) ? (String(rawValue).split('.')[1]?.length ?? 1) : 0
  const displayValue = animated != null ? animated.toFixed(casas) : '—'
```

Trocar o `<span>` do valor (que hoje mostra `{last?.value ?? '—'}`) por:
```tsx
        <span
          key={rawValue ?? 'none'}
          className="font-bold tabular-nums text-[clamp(1.25rem,8cqw,2.25rem)] motion-reduce:animate-none"
          style={{ color: cor, animation: 'kpi-bump var(--dur-slow) var(--ease-overshoot)' }}
        >
          {displayValue}
        </span>
```

(O `key={rawValue}` faz o React remontar o span a cada novo valor, reiniciando a animação `kpi-bump`. A cor do bump no pico é opcional; mantido só o scale para não conflitar com a cor de estado já aplicada.)

- [ ] **Step 6: Ajustar/rodar testes do KpiWidget**

Run: `npm test -- KpiWidget`
Expected: PASS. Se algum teste asserta o texto exato do valor (ex.: `4.2`), ele continua válido — sob reduced-motion (default do setup, `matches:false`... atenção: default é `matches:false`, então o count-up ANIMA). Se um teste checa o valor final renderizado sincronamente e falhar por causa da interpolação, ajustar o teste para usar `findByText`/`waitFor` no valor final, OU forçar reduced-motion no teste via `vi.stubGlobal('matchMedia', ...matches:true...)`. Mostrar o ajuste mínimo necessário conforme o teste que quebrar.

- [ ] **Step 7: Rodar suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/useCountUp.ts frontend/src/lib/useCountUp.test.ts frontend/src/components/widgets/KpiWidget.tsx
git commit -m "feat(dashboard): KPI count-up + bump ao novo valor"
```

---

### Task 3: Transição do carrossel (B) + dots verticais na AreaCard

Troca de sensor com cross-fade + subida; dots movidos para coluna vertical à esquerda, centralizada.

**Files:**
- Modify: `frontend/src/components/AreaCard.tsx` (bloco de render do sensor ativo, ~linhas 140-185)

**Interfaces:**
- Consumes: `carousel.activeIndex` de `useSensorCarousel` (já existe); tokens `--dur-base`, `--ease-out-soft` (Task 1); keyframe `carousel-in` (Task 1).
- Produces: nenhum export novo.

- [ ] **Step 1: Escrever teste do layout dos dots (falha)**

Em `frontend/src/components/AreaCard.test.tsx`, adicionar um teste que garante que, com múltiplos sensores, os dots (`role="tab"`) existem e o container é vertical. Como a orientação é via classe, asseguramos a classe do container de dots:

```tsx
it('dots do carrossel ficam em coluna vertical (tablist com flex-col)', () => {
  renderAreaCardComVariosSensores() // helper já usado nos testes desta suite
  const tablist = screen.getByRole('tablist', { name: /sensores da área/i })
  expect(tablist.className).toMatch(/flex-col/)
})
```

(Se não houver helper `renderAreaCardComVariosSensores`, replicar o setup de um teste existente da mesma suíte que já monta AreaCard com >1 sensor.)

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- AreaCard`
Expected: FAIL (tablist ainda é horizontal, sem `flex-col`).

- [ ] **Step 3: Implementar layout vertical dos dots + wrapper do valor animado**

Em `frontend/src/components/AreaCard.tsx`, reorganizar o corpo (`<div className="mt-2 flex flex-1 flex-col justify-between">`). Envolver o botão do sensor + dots numa linha horizontal onde os dots ficam à ESQUERDA (coluna vertical centrada) e o valor à direita.

Substituir o bloco atual (do `<button ...>` até o fechamento do bloco de dots) por:

```tsx
      <div className="mt-2 flex flex-1 items-center gap-3">
        {group.sensors.length > 1 && (
          <div
            className="flex flex-col items-center justify-center gap-1.5"
            role="tablist"
            aria-label="Sensores da área"
          >
            {group.sensors.map((s, i) => (
              <button
                key={s.sensor_code}
                type="button"
                role="tab"
                aria-selected={i === carousel.activeIndex}
                aria-label={s.measurement_type.name}
                onClick={() => carousel.setActiveIndex(i)}
                className="size-1.5 rounded-full transition-[background,transform] duration-200 ease-out motion-reduce:transition-none"
                style={{
                  background: i === carousel.activeIndex ? 'var(--color-ink)' : 'var(--color-line)',
                  transform: i === carousel.activeIndex ? 'scale(1.15)' : 'scale(1)',
                }}
              />
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => onSelectSensor(activeSensor.sensor_code)}
          className="flex min-w-0 flex-1 flex-col items-start gap-1 rounded-md px-2 py-2 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
          style={{ background: activeSelected ? 'var(--color-panel)' : 'transparent' }}
        >
          <span
            key={activeSensor.sensor_code}
            className="flex w-full flex-col items-start gap-1 motion-reduce:animate-none"
            style={{ animation: 'carousel-in var(--dur-base) var(--ease-out-soft)' }}
          >
            <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
              <span data-testid="sensor-status-dot">
                <StatusDot state={dotState} />
              </span>
              {activeSensor.measurement_type.name}
              {activeFreshness !== 'fresh' && <FreshnessBadge tier={activeFreshness} ageMs={activeAgeMs} />}
            </span>
            <span
              className="font-mono text-3xl font-bold tabular-nums"
              style={{
                color: activeState === 'ok' || activeState === 'unknown' ? 'var(--color-ink)' : statusTextColor(activeState),
                opacity: valueOpacity,
              }}
            >
              {displayValue}{' '}
              <span className="text-base font-medium">{activeSensor.unidade}</span>
            </span>
          </span>
        </button>
      </div>
```

O `key={activeSensor.sensor_code}` no `<span>` interno remonta o conteúdo a cada troca de sensor, disparando `carousel-in` (cross-fade + subida). `motion-reduce:animate-none` desliga sob reduced-motion.

Nota: remover o antigo bloco `{group.sensors.length > 1 && (<div className="mt-2 flex items-center justify-center gap-1.5" ...dots horizontais...)}` — foi absorvido acima.

- [ ] **Step 4: Rodar teste do dot vertical + suite AreaCard**

Run: `npm test -- AreaCard`
Expected: PASS. Ajustar quaisquer testes que dependiam da posição horizontal dos dots (ex.: assert de classe `justify-center` no rodapé). O `role="tablist"`, `role="tab"`, `aria-selected` e `aria-label` foram preservados — testes de a11y/interação seguem válidos.

- [ ] **Step 5: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx
git commit -m "feat(dashboard): carrossel cross-fade + dots verticais na AreaCard"
```

---

### Task 4: Entrada escalonada + hover dos widgets

Widgets entram com fade+subida escalonados no mount; hover eleva 5px.

**Files:**
- Modify: `frontend/src/components/DashboardGrid.tsx` (o `.map` que renderiza `<div key={w.id}><WidgetFrame/></div>`, ~linha 140)

**Interfaces:**
- Consumes: keyframe `widget-in`, tokens `--dur-slow`, `--ease-out-soft` (Task 1).
- Produces: nenhum export novo.

- [ ] **Step 1: Escrever teste da classe de entrada (falha)**

Em `frontend/src/components/DashboardGrid.test.tsx`, adicionar:

```tsx
it('cada widget recebe a classe de entrada animada', () => {
  renderDashboardGrid() // helper/setup já usado na suíte
  const frames = screen.getAllByTestId('widget-frame')
  // O wrapper de grid de cada widget carrega a classe de animação de entrada.
  frames.forEach((f) => {
    const wrapper = f.parentElement as HTMLElement
    expect(wrapper.className).toMatch(/animate-widget-in|widget-enter/)
  })
})
```

(Usar o setup já existente da suíte para montar o grid com widgets.)

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- DashboardGrid`
Expected: FAIL (wrapper sem a classe).

- [ ] **Step 3: Implementar entrada escalonada + hover**

Em `frontend/src/components/DashboardGrid.tsx`, trocar o `.map` final:

```tsx
        {layout.widgets.map((w, i) => (
          <div
            key={w.id}
            className="widget-enter motion-reduce:animate-none"
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <WidgetFrame
              widget={w}
              editing={editing}
              onChange={onWidgetChange}
              onRemove={onRemove ? () => onRemove(w.id) : undefined}
            />
          </div>
        ))}
```

Adicionar a classe `.widget-enter` e o hover ao fim de `frontend/src/index.css`:

```css
/* Entrada escalonada dos widgets no mount da grade + hover de elevação.
   O hover fica no wrapper de grid (filho direto do react-grid-layout). */
.widget-enter {
  animation: widget-in var(--dur-slow) var(--ease-out-soft) both;
}
.widget-enter > * {
  transition: transform var(--dur-fast) var(--ease-out-soft), box-shadow var(--dur-fast) ease;
}
.widget-enter:hover > * {
  transform: translateY(-5px);
  box-shadow: 0 10px 26px rgb(0 0 0 / 0.4);
}
@media (prefers-reduced-motion: reduce) {
  .widget-enter { animation: none; }
  .widget-enter:hover > * { transform: none; }
}
```

Nota: no modo edição (`dashboard-grid-editing`), o hover-elevate pode conflitar com drag. Restringir o hover ao modo não-edição:

```css
.dashboard-grid-editing .widget-enter:hover > * { transform: none; box-shadow: none; }
```

- [ ] **Step 4: Rodar teste da entrada + suite grid**

Run: `npm test -- DashboardGrid`
Expected: PASS.

- [ ] **Step 5: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DashboardGrid.tsx frontend/src/index.css
git commit -m "feat(dashboard): entrada escalonada + hover 5px dos widgets"
```

---

### Task 5: Alarme novo — slide de entrada + flash de 5s

Novo alarme desliza do topo e recebe flash de destaque que desvanece em 5s; o alarme permanece.

**Files:**
- Modify: `frontend/src/components/AlarmItem.tsx` (aceitar prop `isNew`)
- Modify: `frontend/src/components/AlarmPanel.tsx` (detectar itens novos por diff de IDs entre renders, passar `isNew`)

**Interfaces:**
- Consumes: keyframe `alarm-in`, tokens `--dur-base`/`--ease-out-soft` (Task 1); `AlarmEvent` de `../lib/types`.
- Produces: `AlarmItem` ganha prop opcional `isNew?: boolean`. Chave estável de alarme para o diff: `` `${alarm.sensor_code}-${alarm.timestamp_deteccao}` ``.

- [ ] **Step 1: Escrever teste do AlarmItem (falha)**

Em `frontend/src/components/AlarmItem.test.tsx` (criar se não existir):

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

const base: AlarmEvent = {
  sensor_code: 'TEMP-01', area_code: 'A1', status: 'aberto',
  valor_lido: 8.1, limite_configurado_snapshot: 6,
  timestamp_deteccao: 1_700_000_000_000,
} as AlarmEvent

describe('AlarmItem', () => {
  it('sem isNew: não aplica animação de entrada', () => {
    render(<ul><AlarmItem alarm={base} areaName="Câmara" /></ul>)
    const li = screen.getByRole('listitem')
    expect(li.className).not.toMatch(/alarm-enter/)
  })
  it('isNew: aplica classe de entrada/flash', () => {
    render(<ul><AlarmItem alarm={base} areaName="Câmara" isNew /></ul>)
    const li = screen.getByRole('listitem')
    expect(li.className).toMatch(/alarm-enter/)
  })
})
```

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- AlarmItem`
Expected: FAIL (prop `isNew` inexistente / classe ausente).

- [ ] **Step 3: Implementar `isNew` no AlarmItem**

Em `frontend/src/components/AlarmItem.tsx`, alterar a assinatura e o `<li>`:

```tsx
export function AlarmItem({ alarm, areaName, isNew }: { alarm: AlarmEvent; areaName: string; isNew?: boolean }) {
  return (
    <li
      className={`rounded-md p-3${isNew ? ' alarm-enter motion-reduce:animate-none' : ''}`}
      style={{ background: 'var(--color-panel)', borderLeft: `3px solid ${BORDER_COLOR[alarm.status]}` }}
    >
```

Adicionar ao fim de `frontend/src/index.css` a classe (slide de entrada + flash de 5s que volta ao fundo normal):

```css
/* Alarme recém-chegado: desliza do topo (rápido) + flash de destaque que
   desvanece em 5s. O alarme PERMANECE na lista — o flash é só realce. */
.alarm-enter {
  animation:
    alarm-in var(--dur-base) var(--ease-out-soft) both,
    alarm-flash 5s ease-out both;
}
@keyframes alarm-flash {
  from { background: var(--color-crit-soft); }
  to   { background: var(--color-panel); }
}
@media (prefers-reduced-motion: reduce) {
  .alarm-enter { animation: none; }
}
```

- [ ] **Step 4: Rodar teste do AlarmItem**

Run: `npm test -- AlarmItem`
Expected: PASS.

- [ ] **Step 5: Detectar novos no AlarmPanel e passar `isNew`**

Em `frontend/src/components/AlarmPanel.tsx`, importar hooks e computar o conjunto de IDs vistos no render anterior. Adicionar no topo do arquivo:

```tsx
import { useEffect, useRef, type ReactNode } from 'react'
```

Dentro do componente, antes do `return`:

```tsx
  const keyOf = (a: AlarmEvent) => `${a.sensor_code}-${a.timestamp_deteccao}`
  const seenRef = useRef<Set<string> | null>(null)
  const currentKeys = new Set(visiveis.map(keyOf))
  // Primeiro render: nada é "novo" (não animar a lista inicial inteira).
  const novos = seenRef.current === null
    ? new Set<string>()
    : new Set([...currentKeys].filter((k) => !seenRef.current!.has(k)))
  useEffect(() => {
    seenRef.current = currentKeys
  })
```

(`visiveis` já existe: `alarms.slice(0, VISIBLE_LIMIT)`.)

No `.map` que renderiza os `AlarmItem` (dentro da lista `visiveis`), passar `isNew`:

```tsx
        <AlarmItem
          key={keyOf(alarm)}
          alarm={alarm}
          areaName={areaNameByCode[alarm.area_code] ?? alarm.area_code}
          isNew={novos.has(keyOf(alarm))}
        />
```

(Se o `key` atual usa outra expressão, trocar para `keyOf(alarm)` para casar com o diff. Confirmar o nome exato da variável de item no `.map` existente — ver AlarmPanel linhas após `mensagemVazio`.)

- [ ] **Step 6: Rodar suite AlarmPanel + AlarmsWidget**

Run: `npm test -- AlarmPanel AlarmsWidget AlarmItem`
Expected: PASS. Se algum teste do AlarmPanel montar a lista e não esperar a classe, ok (primeiro render nunca marca novos).

- [ ] **Step 7: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/AlarmItem.tsx frontend/src/components/AlarmItem.test.tsx frontend/src/components/AlarmPanel.tsx frontend/src/index.css
git commit -m "feat(dashboard): alarme novo desliza + flash de 5s"
```

---

### Task 6: Drill-down — slide do drawer + bottom sheet responsivo

Painel de detalhe desliza da direita no desktop e sobe como bottom sheet no mobile; backdrop com fade.

**Files:**
- Modify: `frontend/src/components/SensorDetailDrawer.tsx` (o `<div role="dialog">` e o `FloatingOverlay`)

**Interfaces:**
- Consumes: tokens `--dur-base`/`--ease-out-soft` (Task 1). Sem novos exports.
- Produces: classes CSS `drawer-panel` (responsiva) e `drawer-backdrop` (fade), adicionadas em `index.css`.

Nota: o drawer monta/desmonta via estado do pai (T3 do D3 original). Como não há fase de "exit" sem AnimatePresence, animamos só a ENTRADA (mount) com keyframe; o fechamento é imediato (aceitável — o backdrop some junto). Isso respeita o "sem dependência nova".

- [ ] **Step 1: Escrever teste de classe responsiva (falha)**

Em `frontend/src/components/SensorDetailDrawer.test.tsx` (usar setup existente que monta o drawer com um sensorCode válido), adicionar:

```tsx
it('painel usa classe responsiva de slide (drawer-panel)', () => {
  renderDrawer('TEMP-01') // helper/setup existente
  const dialog = screen.getByRole('dialog')
  expect(dialog.className).toMatch(/drawer-panel/)
})
```

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- SensorDetailDrawer`
Expected: FAIL (classe ausente).

- [ ] **Step 3: Implementar classes no drawer**

Em `frontend/src/components/SensorDetailDrawer.tsx`:

No `FloatingOverlay`, adicionar a classe `drawer-backdrop` (mantendo `z-40` e o `style` de background):
```tsx
      <FloatingOverlay
        data-testid="sensor-detail-drawer-backdrop"
        lockScroll
        className="z-40 drawer-backdrop"
        style={{ background: 'rgb(0 0 0 / 0.5)' }}
      >
```

No `<div role="dialog">`, trocar o `className` para incluir `drawer-panel` e remover o posicionamento fixo `right-0 top-0 ... h-screen` (agora vem do CSS responsivo):
```tsx
          <div
            ref={refs.setFloating}
            role="dialog"
            aria-modal="true"
            aria-label={`Detalhe do sensor ${sensor.name}`}
            className="drawer-panel z-50 flex flex-col motion-reduce:animate-none"
            style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-menu)' }}
            {...getFloatingProps()}
          >
```

(Remover o `style={{ width: 'min(560px, 100vw)' }}` inline — a largura/altura passam para o CSS por breakpoint.)

Adicionar ao fim de `frontend/src/index.css`:

```css
/* Drawer de detalhe do sensor: desliza da direita no desktop; vira bottom
   sheet (sobe de baixo) no mobile. Backdrop com fade. Só a entrada anima
   (mount) — sem lib de exit. */
.drawer-backdrop { animation: drawer-fade var(--dur-base) ease both; }
@keyframes drawer-fade { from { opacity: 0; } to { opacity: 1; } }

.drawer-panel {
  position: fixed;
  right: 0;
  top: 0;
  height: 100vh;
  width: min(560px, 100vw);
  animation: drawer-slide-right var(--dur-base) var(--ease-out-soft) both;
}
@keyframes drawer-slide-right {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}
/* Mobile: bottom sheet */
@media (max-width: 640px) {
  .drawer-panel {
    top: auto;
    bottom: 0;
    right: 0;
    left: 0;
    width: 100%;
    height: 80vh;
    animation: drawer-slide-up var(--dur-base) var(--ease-out-soft) both;
  }
  @keyframes drawer-slide-up {
    from { transform: translateY(100%); }
    to   { transform: translateY(0); }
  }
}
@media (prefers-reduced-motion: reduce) {
  .drawer-backdrop, .drawer-panel { animation: none; }
}
```

- [ ] **Step 4: Rodar teste do drawer**

Run: `npm test -- SensorDetailDrawer`
Expected: PASS. O `role="dialog"`, `aria-modal`, focus trap, backdrop-close e Esc foram preservados (só trocamos classes/estilos de layout) — testes de a11y/dismiss seguem válidos.

- [ ] **Step 5: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SensorDetailDrawer.tsx frontend/src/index.css
git commit -m "feat(dashboard): drawer slide + bottom sheet responsivo"
```

---

### Task 7: Chips (tap) + ThemeToggle (swap de ícone)

Feedback de tap nos chips de filtro e transição no toggle de tema.

**Files:**
- Modify: `frontend/src/components/widgets/AlarmsWidget.tsx` (constante `chipPillClass`)
- Modify: `frontend/src/components/ThemeToggle.tsx` (ícone com transição)

**Interfaces:**
- Consumes: nada novo além de utilitários Tailwind.
- Produces: nenhum export novo.

- [ ] **Step 1: Escrever teste do chip (falha)**

Em `frontend/src/components/widgets/AlarmsWidget.test.tsx`, adicionar (usar setup existente que renderiza os chips):

```tsx
it('pill dos chips tem feedback de tap (active:scale)', () => {
  renderAlarmsWidgetComAreas() // setup existente com >0 áreas
  const pill = screen.getByText('Todas')
  expect(pill.className).toMatch(/active:scale-95/)
})
```

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- AlarmsWidget`
Expected: FAIL (classe ausente).

- [ ] **Step 3: Implementar tap no chip**

Em `frontend/src/components/widgets/AlarmsWidget.tsx`, alterar `chipPillClass`:

```tsx
  const chipPillClass =
    'rounded-full px-2 py-1 text-[11px] font-medium transition-[background-color,color,transform] duration-200 ease-out active:scale-95 motion-reduce:transition-none motion-reduce:active:scale-100'
```

- [ ] **Step 4: Rodar teste do chip**

Run: `npm test -- AlarmsWidget`
Expected: PASS.

- [ ] **Step 5: Transição no ThemeToggle (swap de ícone)**

O ThemeToggle é botão texto+ícone (não knob). Animar a troca de ícone com rotate+fade ao alternar. Em `frontend/src/components/ThemeToggle.tsx`, envolver o ícone com um `<span>` que remonta por `key` (dispara a animação) e adicionar a classe:

```tsx
      <span
        key={control ? 'sun' : 'moon'}
        className="inline-flex motion-reduce:animate-none"
        style={{ animation: 'icon-swap var(--dur-base) var(--ease-overshoot)' }}
      >
        {control ? <SunIcon /> : <MoonIcon />}
      </span>
      <span>{control ? 'Claro' : 'Escuro'}</span>
```

Adicionar o keyframe ao fim de `frontend/src/index.css`:

```css
/* Swap de ícone do toggle de tema: leve rotação + fade ao alternar. */
@keyframes icon-swap {
  from { opacity: 0; transform: rotate(-30deg) scale(0.8); }
  to   { opacity: 1; transform: rotate(0) scale(1); }
}
```

- [ ] **Step 6: Rodar suite ThemeToggle + AlarmsWidget**

Run: `npm test -- ThemeToggle AlarmsWidget`
Expected: PASS. O `aria-pressed`/`aria-label` do ThemeToggle foram preservados.

- [ ] **Step 7: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/widgets/AlarmsWidget.tsx frontend/src/components/ThemeToggle.tsx frontend/src/index.css
git commit -m "feat(dashboard): tap nos chips + swap de ícone no tema"
```

---

### Task 8: Modo editor — fade do grid overlay + wobble dos widgets

Grid overlay aparece com fade; widgets balançam sutilmente para sinalizar "arrastável".

**Files:**
- Modify: `frontend/src/components/DashboardGrid.tsx` (`EditGridOverlay` classes)
- Modify: `frontend/src/index.css` (fade do overlay + wobble via `.dashboard-grid-editing`)

**Interfaces:**
- Consumes: keyframe `editor-wobble` (Task 1), classe `dashboard-grid-editing` (já aplicada ao container quando `editing`), classe `widget-enter` (Task 4, nos wrappers de widget).
- Produces: nenhum export novo.

- [ ] **Step 1: Escrever teste do fade do overlay (falha)**

Em `frontend/src/components/DashboardGrid.test.tsx`, adicionar:

```tsx
it('overlay de edição tem classe de fade', () => {
  renderDashboardGrid({ editing: true }) // setup existente com editing
  const overlay = screen.getByTestId('edit-grid-overlay')
  expect(overlay.className).toMatch(/edit-grid-fade/)
})
```

- [ ] **Step 2: Rodar p/ falhar**

Run: `npm test -- DashboardGrid`
Expected: FAIL (classe ausente).

- [ ] **Step 3: Implementar fade do overlay + wobble**

Em `frontend/src/components/DashboardGrid.tsx`, no `EditGridOverlay`, adicionar `edit-grid-fade` ao className:

```tsx
    <div
      data-testid="edit-grid-overlay"
      className="edit-grid-fade pointer-events-none absolute inset-0 rounded"
      style={style}
    />
```

Adicionar ao fim de `frontend/src/index.css`:

```css
/* Modo editor: grid overlay entra com fade; widgets balançam de leve para
   sinalizar que são arrastáveis. Movimento contínuo é o mais sensível a
   reduced-motion — desligado lá. */
.edit-grid-fade { animation: drawer-fade var(--dur-base) ease both; }

.dashboard-grid-editing .widget-enter {
  animation: editor-wobble 1.8s ease-in-out infinite;
}
.dashboard-grid-editing .widget-enter:nth-child(2n)  { animation-delay: 0.2s; }
.dashboard-grid-editing .widget-enter:nth-child(3n)  { animation-delay: 0.4s; }

@media (prefers-reduced-motion: reduce) {
  .edit-grid-fade { animation: none; }
  .dashboard-grid-editing .widget-enter { animation: none; }
}
```

Nota: o `editing` do `DashboardGrid` renderizado pela DashboardPage em modo edição usa o próprio `DashboardGrid` (a página passa `editing`); confirmar que o container recebe `dashboard-grid-editing` (já ocorre: `className={...editing ? ' dashboard-grid-editing' : ''}`). O wobble só roda quando o container tem essa classe.

Cuidado de conflito: no modo edição os widgets usam `editor-wobble` (infinite), que sobrescreve o `widget-in` de entrada — ok, porque a entrada só importa fora da edição. Verificar visualmente que ao SAIR da edição o `widget-in` não re-dispara indesejadamente (não deve: a classe `.widget-enter` é a mesma, mas sem `.dashboard-grid-editing` volta a `widget-in`, que roda `both` uma vez no mount — não re-anima em toggle de estado, pois o nó não remonta). Se re-animar, aceitar (é sutil) ou mover o wobble para uma classe separada aplicada condicionalmente.

- [ ] **Step 4: Rodar teste do overlay**

Run: `npm test -- DashboardGrid`
Expected: PASS.

- [ ] **Step 5: Suite completa**

Run: `npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DashboardGrid.tsx frontend/src/index.css
git commit -m "feat(dashboard): fade do grid + wobble no modo editor"
```

---

### Task 9: Verificação visual no browser (Playwright)

Validação manual/roteirizada das 8 superfícies (chrome-devtools-mcp não sobe em WSL2 — usar Playwright, padrão do projeto).

**Files:**
- Usar o app rodando local (`npm run dev`) com dados mock (`.env.mock.local`, padrão do projeto).

- [ ] **Step 1: Subir o app em modo mock**

Run (de `frontend/`): `npm run dev` (com o modo mock do projeto). Abrir a dashboard.

- [ ] **Step 2: Checklist visual**

Verificar, em tema escuro (`.theme-control`, default) e claro:
- Carrossel: troca de sensor faz cross-fade + subida; dots verticais à esquerda, ativo destacado.
- Widgets: entram escalonados no load; hover eleva 5px + sombra (fora da edição).
- Alarme: ao injetar um alarme mock novo, ele desliza do topo e o fundo faz flash que some em ~5s; alarme permanece.
- KPI: ao mudar o valor mock, conta até o novo valor + bump.
- Drill-down: clicar num sensor abre o painel deslizando (direita no desktop; reduzir a janela p/ mobile e ver bottom sheet); backdrop faz fade.
- Chips: tap dá um leve scale.
- Tema: alternar troca o ícone com rotate+fade.
- Editor: entrar em edição mostra grid (fade) e widgets com wobble sutil.

- [ ] **Step 3: Verificar reduced-motion**

Nas DevTools (Rendering → Emulate `prefers-reduced-motion: reduce`), confirmar que TODAS as superfícies degradam para instantâneo (sem transform/keyframe; carrossel troca seco; sem wobble).

- [ ] **Step 4: Rodar lint + build final**

Run: `npm run lint && npm run build`
Expected: sem erros.

- [ ] **Step 5: Commit (se houver ajustes de verificação)**

```bash
git add -A
git commit -m "chore(dashboard): ajustes da verificação visual de animações"
```

---

## Self-Review

**Spec coverage:**
- §Princípios (tokens, reduced-motion, sem dep) → Task 1 + Global Constraints. ✅
- §1 Carrossel → Task 3. ✅
- §2 Widgets entrada/hover → Task 4. ✅
- §3 Alarme flash 5s → Task 5. ✅
- §4 KPI count-up/bump → Task 2. ✅
- §5 Drill-down responsivo → Task 6. ✅
- §6 Chips tap → Task 7. ✅
- §7 Tema → Task 7 (adaptado: swap de ícone, não knob — componente real é botão texto+ícone). ✅
- §8 Editor overlay+wobble → Task 8. ✅
- §Testes → cada task + Task 9 (visual). ✅

**Placeholder scan:** sem TBD/TODO; todo passo com código/comando concreto. Alguns passos pedem "usar setup/helper existente da suíte" — isso é referência a padrão real dos testes do projeto, não placeholder de lógica.

**Type consistency:** `useCountUp(target: number | null, opts?)` usado igual no KpiWidget. `AlarmItem` prop `isNew?: boolean` consumida no AlarmPanel com a mesma `keyOf`. Classes CSS (`widget-enter`, `alarm-enter`, `drawer-panel`, `drawer-backdrop`, `edit-grid-fade`, `carousel-in`) definidas em Task 1/4/5/6/8 e referenciadas de forma consistente. `drawer-fade` (keyframe) reusado por `edit-grid-fade` (definido em Task 6, usado em Task 8 — Task 6 precede Task 8). ✅
