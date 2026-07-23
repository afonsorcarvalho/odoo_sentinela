# KPI — formato numérico configurável Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir configurar, por widget KPI, o nº mínimo de dígitos inteiros (zero-pad) e o nº de casas decimais do valor exibido.

**Architecture:** Um helper puro `formatKpi` centraliza a formatação (testável isolado). O schema Zod ganha 2 campos opcionais degradáveis. O widget consome o helper; o registry repassa as options; o popover ganha 2 inputs numéricos.

**Tech Stack:** React + TypeScript, Vitest + @testing-library/react, Zod.

## Global Constraints

- **Backward-compat dura:** widget KPI sem `casasDecimais` e sem `digitosInteiros` = comportamento **idêntico ao atual** (auto-detecta decimais do valor bruto, cap 3; sem padding).
- Campos de options seguem o padrão existente `.optional().catch(undefined)` (degrada campo a campo, nunca lança).
- Diretório de trabalho dos comandos: `frontend/`. Rodar testes com `npx vitest run <arquivo>`.
- Zero-pad é **mínimo**: nunca corta dígitos reais do valor (padding menor que o inteiro presente = no-op).

---

### Task 1: Helper `formatKpi` + `autoCasas`

**Files:**
- Create: `frontend/src/lib/kpiFormat.ts`
- Test: `frontend/src/lib/kpiFormat.test.ts`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `export function autoCasas(value: number): number` — 0 se inteiro; senão `min(len(fração), 3)`.
  - `export function formatKpi(value: number, opts: { casasDecimais?: number; digitosInteiros?: number }): string`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/kpiFormat.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { autoCasas, formatKpi } from './kpiFormat'

describe('autoCasas', () => {
  it('inteiro -> 0', () => {
    expect(autoCasas(130)).toBe(0)
    expect(autoCasas(-7)).toBe(0)
  })
  it('detecta casas da fração', () => {
    expect(autoCasas(5.1)).toBe(1)
    expect(autoCasas(19.06)).toBe(2)
  })
  it('cap em 3 casas', () => {
    expect(autoCasas(1.23456)).toBe(3)
  })
})

describe('formatKpi', () => {
  it('sem opts -> auto (idêntico ao comportamento atual)', () => {
    expect(formatKpi(19.063, {})).toBe('19.063')
    expect(formatKpi(130, {})).toBe('130')
    expect(formatKpi(1.23456, {})).toBe('1.235')
  })
  it('casasDecimais fixa as decimais (arredonda)', () => {
    expect(formatKpi(19.063, { casasDecimais: 2 })).toBe('19.06')
    expect(formatKpi(5.1, { casasDecimais: 3 })).toBe('5.100')
    expect(formatKpi(19.063, { casasDecimais: 0 })).toBe('19')
  })
  it('digitosInteiros faz zero-pad da parte inteira', () => {
    expect(formatKpi(19.063, { casasDecimais: 2, digitosInteiros: 3 })).toBe('019.06')
    expect(formatKpi(5.1, { casasDecimais: 1, digitosInteiros: 3 })).toBe('005.1')
    expect(formatKpi(130, { casasDecimais: 0, digitosInteiros: 5 })).toBe('00130')
  })
  it('preserva sinal negativo no zero-pad', () => {
    expect(formatKpi(-5.1, { casasDecimais: 1, digitosInteiros: 3 })).toBe('-005.1')
  })
  it('padding menor que o inteiro presente é no-op (não corta)', () => {
    expect(formatKpi(12345, { casasDecimais: 0, digitosInteiros: 2 })).toBe('12345')
  })
  it('digitosInteiros sem casasDecimais usa auto nas decimais', () => {
    expect(formatKpi(5.1, { digitosInteiros: 3 })).toBe('005.1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/kpiFormat.test.ts` (a partir de `frontend/`)
Expected: FAIL — `Failed to resolve import './kpiFormat'` / função não definida.

- [ ] **Step 3: Write minimal implementation**

`frontend/src/lib/kpiFormat.ts`:

```ts
// Formatação numérica do valor KPI. Puro e testável isolado.
// `autoCasas` preserva a heurística histórica do KpiWidget (cap 3 casas).
export function autoCasas(value: number): number {
  if (Number.isInteger(value)) return 0
  const frac = String(value).split('.')[1]
  return Math.min(frac?.length ?? 1, 3)
}

// Formata `value` com um nº fixo de casas decimais (ou auto) e, opcionalmente,
// zero-pad da parte inteira a um mínimo de dígitos. O padding NUNCA corta:
// se a parte inteira já tem mais dígitos que o mínimo, fica como está.
export function formatKpi(
  value: number,
  opts: { casasDecimais?: number; digitosInteiros?: number },
): string {
  const decimais = opts.casasDecimais ?? autoCasas(value)
  const s = value.toFixed(decimais) // produz o sinal '-' quando negativo
  if (opts.digitosInteiros == null) return s

  const negativo = s.startsWith('-')
  const semSinal = negativo ? s.slice(1) : s
  const ponto = semSinal.indexOf('.')
  const inteiro = ponto === -1 ? semSinal : semSinal.slice(0, ponto)
  const fracao = ponto === -1 ? '' : semSinal.slice(ponto) // inclui o '.'
  const inteiroPad = inteiro.padStart(opts.digitosInteiros, '0')
  return (negativo ? '-' : '') + inteiroPad + fracao
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/kpiFormat.test.ts`
Expected: PASS (todos os casos).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/kpiFormat.ts frontend/src/lib/kpiFormat.test.ts
git commit -m "feat(kpi): helper puro formatKpi (zero-pad inteiros + casas decimais)"
```

---

### Task 2: Schema — campos `casasDecimais` e `digitosInteiros` em `kpiOptions`

**Files:**
- Modify: `frontend/src/lib/layout/schema.ts:20-29`
- Test: `frontend/src/lib/layout/schema.test.ts`

**Interfaces:**
- Consumes: nada.
- Produces: `OPTIONS_SCHEMA.kpi` passa a aceitar `casasDecimais?: number` (int 0–6) e `digitosInteiros?: number` (int 1–12); inválidos → `undefined`.

- [ ] **Step 1: Write the failing test**

Adicionar em `frontend/src/lib/layout/schema.test.ts`, dentro do `describe('OPTIONS_SCHEMA', ...)`:

```ts
  it('kpi: casasDecimais e digitosInteiros válidos são preservados', () => {
    const r = OPTIONS_SCHEMA.kpi.parse({ casasDecimais: 2, digitosInteiros: 3 })
    expect(r).toMatchObject({ casasDecimais: 2, digitosInteiros: 3 })
  })
  it('kpi: casasDecimais fora do range vira undefined (catch)', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({ casasDecimais: 99 }).casasDecimais).toBeUndefined()
    expect(OPTIONS_SCHEMA.kpi.parse({ casasDecimais: -1 }).casasDecimais).toBeUndefined()
  })
  it('kpi: digitosInteiros inválido (0 ou string) vira undefined (catch)', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({ digitosInteiros: 0 }).digitosInteiros).toBeUndefined()
    expect(OPTIONS_SCHEMA.kpi.parse({ digitosInteiros: 'x' as unknown as number }).digitosInteiros).toBeUndefined()
  })
```

Atualizar também o teste existente `kpi: defaults quando ausente/vazio` (linhas ~65-71) para incluir os novos campos:

```ts
  it('kpi: defaults quando ausente/vazio', () => {
    expect(OPTIONS_SCHEMA.kpi.parse({})).toEqual({
      label: undefined,
      limiteMin: undefined,
      limiteMax: undefined,
      casasDecimais: undefined,
      digitosInteiros: undefined,
    })
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/layout/schema.test.ts`
Expected: FAIL nos 3 casos novos (campos preservados/clamp) — `casasDecimais` inexistente no schema, `parse` ignora e retorna undefined onde o teste espera valor preservado.

- [ ] **Step 3: Write minimal implementation**

Em `frontend/src/lib/layout/schema.ts`, dentro do `z.object` de `kpiOptions` (após `limiteMax`):

```ts
const kpiOptions = z
  .object({
    label: z.string().optional().catch(undefined),
    limiteMin: z.number().optional().catch(undefined), // override display-only (§KPI)
    limiteMax: z.number().optional().catch(undefined), // NUNCA suaviza alarm_state
    casasDecimais: z.number().int().min(0).max(6).optional().catch(undefined), // nº fixo de decimais; ausente = auto
    digitosInteiros: z.number().int().min(1).max(12).optional().catch(undefined), // zero-pad mín. da parte inteira
  })
  .refine(
    (o) => o.limiteMin == null || o.limiteMax == null || o.limiteMin <= o.limiteMax,
    { message: 'limiteMin deve ser ≤ limiteMax' },
  )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/layout/schema.test.ts`
Expected: PASS (todos, incluindo os 3 novos e o `defaults` atualizado).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/layout/schema.ts frontend/src/lib/layout/schema.test.ts
git commit -m "feat(kpi): schema casasDecimais + digitosInteiros (opcionais, degradáveis)"
```

---

### Task 3: KpiWidget consome `formatKpi` + registry repassa options

**Files:**
- Modify: `frontend/src/components/widgets/KpiWidget.tsx:27-57`
- Modify: `frontend/src/lib/widgets/registry.tsx:49-56`
- Test: `frontend/src/components/widgets/KpiWidget.test.tsx`

**Interfaces:**
- Consumes: `formatKpi` (Task 1); options do schema (Task 2).
- Produces: `KpiWidget` aceita props `casasDecimais?: number`, `digitosInteiros?: number`.

- [ ] **Step 1: Write the failing test**

Adicionar em `frontend/src/components/widgets/KpiWidget.test.tsx`, novo `describe` no fim do `describe('KpiWidget', ...)`:

```ts
  describe('formato numérico configurável', () => {
    it('sem config -> auto (não regride): 19.063 exibe 19.063', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 19.063, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" />)
      expect(screen.getByText('19.063')).toBeInTheDocument()
    })
    it('casasDecimais=2 -> 19.06', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 19.063, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" casasDecimais={2} />)
      expect(screen.getByText('19.06')).toBeInTheDocument()
    })
    it('digitosInteiros=3 + casasDecimais=2 -> 019.06 (zero-pad)', () => {
      mockUseLiveTail.mockReturnValue({ last: { value: 19.063, alarm_state: 'ok' } })
      renderWithClient(<KpiWidget sensorCode="S1" casasDecimais={2} digitosInteiros={3} />)
      expect(screen.getByText('019.06')).toBeInTheDocument()
    })
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/widgets/KpiWidget.test.tsx`
Expected: FAIL nos casos `19.06`/`019.06` (widget ainda usa `casas` auto, ignora as props inexistentes).

Nota: o count-up (`useCountUp`) não é mockado; os testes atuais já assertam o valor final (ex. `getByText('10')`), então o valor formatado final é o que aparece.

- [ ] **Step 3: Write minimal implementation**

Em `frontend/src/components/widgets/KpiWidget.tsx`:

Adicionar import no topo (junto aos outros de `../../lib`):

```ts
import { formatKpi } from '../../lib/kpiFormat'
```

Estender a assinatura de props (bloco `export function KpiWidget({ ... }: { ... })`, linhas 27-37):

```ts
export function KpiWidget({
  sensorCode,
  label,
  limiteMin,
  limiteMax,
  casasDecimais,
  digitosInteiros,
}: {
  sensorCode: string
  label?: string
  limiteMin?: number
  limiteMax?: number
  casasDecimais?: number
  digitosInteiros?: number
}) {
```

Substituir as linhas 55-57 (bloco `casas`/`displayValue`) por:

```ts
  // Formatação: casasDecimais/digitosInteiros vêm das options do widget; ausentes
  // caem no auto histórico (casas detectadas do valor bruto, cap 3; sem padding).
  const displayValue =
    animated != null ? formatKpi(animated, { casasDecimais, digitosInteiros }) : '—'
```

(Remover a linha 56 `const casas = ...` — agora vive dentro de `formatKpi`/`autoCasas`.)

Em `frontend/src/lib/widgets/registry.tsx`, no `render` do `kpi` (linhas 49-56), passar as 2 props novas:

```tsx
    render: (w) => w.binding.sensorCode
      ? <KpiWidget
          sensorCode={w.binding.sensorCode}
          label={w.options?.label as string | undefined}
          limiteMin={w.options?.limiteMin as number | undefined}
          limiteMax={w.options?.limiteMax as number | undefined}
          casasDecimais={w.options?.casasDecimais as number | undefined}
          digitosInteiros={w.options?.digitosInteiros as number | undefined}
        />
      : <WidgetPlaceholder texto="Configurar sensor" />,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/widgets/KpiWidget.test.tsx`
Expected: PASS (novos casos + todos os antigos, incl. `getByText('10')`, `'25'`, `'-5'`).

- [ ] **Step 5: Verify typecheck**

Run: `npx tsc --noEmit` (a partir de `frontend/`)
Expected: sem erros.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/widgets/KpiWidget.tsx frontend/src/components/widgets/KpiWidget.test.tsx frontend/src/lib/widgets/registry.tsx
git commit -m "feat(kpi): widget aplica formatKpi; registry repassa options de formato"
```

---

### Task 4: UI do popover — inputs "Dígitos inteiros" e "Casas decimais"

**Files:**
- Modify: `frontend/src/components/WidgetConfigPopover.tsx:157-196`
- Test: (opcional) `frontend/src/components/WidgetConfigPopover.test.tsx` se já existir; senão, validação manual pelo typecheck.

**Interfaces:**
- Consumes: `setOption` (já existe no componente); options do schema (Task 2).
- Produces: nenhuma nova API.

- [ ] **Step 1: Verificar se há teste do popover**

Run: `ls frontend/src/components/WidgetConfigPopover.test.tsx 2>/dev/null && echo EXISTE || echo NAO_EXISTE`

Se EXISTE: adicionar teste (Step 2a). Se NAO_EXISTE: pular direto para Step 3 (validação por typecheck + render manual), pois o padrão do projeto não exige teste dedicado deste componente.

- [ ] **Step 2a (só se o teste existir): adicionar caso**

No arquivo de teste do popover, um caso que renderiza um widget kpi, digita "2" no input "Casas decimais" e espera que `onChange` seja chamado com `options.casasDecimais === 2`. Seguir o estilo dos casos existentes de "Limite mín." (mesmo padrão de `fireEvent.change` + assert em `onChange`).

- [ ] **Step 3: Implementar os inputs**

Em `frontend/src/components/WidgetConfigPopover.tsx`, dentro do bloco `widget.type === 'kpi'`, **após** o `<label>` "Limite máx." e **antes** do `{limitesInvalidos && ...}`, inserir:

```tsx
              <label className="block text-xs">Dígitos inteiros (mín.)
                <input
                  type="number"
                  min={1}
                  max={12}
                  placeholder="auto"
                  className={selectClass}
                  style={inputStyle}
                  value={(widget.options?.digitosInteiros as number | undefined) ?? ''}
                  onChange={(e) => setOption({ digitosInteiros: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </label>
              <label className="block text-xs">Casas decimais
                <input
                  type="number"
                  min={0}
                  max={6}
                  placeholder="auto"
                  className={selectClass}
                  style={inputStyle}
                  value={(widget.options?.casasDecimais as number | undefined) ?? ''}
                  onChange={(e) => setOption({ casasDecimais: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </label>
```

- [ ] **Step 4: Typecheck + testes do componente**

Run (a partir de `frontend/`):
```bash
npx tsc --noEmit
npx vitest run src/components/WidgetConfigPopover.test.tsx 2>/dev/null || echo "sem teste dedicado — ok"
```
Expected: tsc sem erros; testes (se houver) PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WidgetConfigPopover.tsx
git commit -m "feat(kpi): inputs de dígitos inteiros e casas decimais no popover de config"
```

---

### Task 5: Verificação final da suíte

**Files:** nenhum (só verificação).

- [ ] **Step 1: Rodar suíte completa do frontend**

Run (a partir de `frontend/`): `npx vitest run`
Expected: todos verdes; nenhuma regressão em KpiWidget/schema/registry.

- [ ] **Step 2: Typecheck completo**

Run: `npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 3 (opcional, se o usuário quiser conferência visual): rodar o dashboard**

Configurar um KPI com `digitosInteiros=3`, `casasDecimais=2` e confirmar `019.06` (largura estável no count-up). Sem config → valor auto como antes.
