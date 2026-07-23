# KPI — formato numérico configurável (dígitos inteiros + casas decimais)

**Data:** 2026-07-23
**Escopo:** frontend Sentinela (widget KPI)

## Problema

O widget KPI formata o valor com casas decimais **auto-detectadas** do valor bruto
(cap 3). O admin não controla quantas casas decimais aparecem nem consegue fixar a
largura do número (zero-pad de dígitos inteiros) para leitura estável.

## Objetivo

Dois campos de configuração **por widget KPI**, ambos opcionais:

- **Casas decimais** (`casasDecimais`): nº fixo de casas após a vírgula.
- **Dígitos inteiros mín.** (`digitosInteiros`): mínimo de dígitos na parte inteira,
  preenchendo com zeros à esquerda (zero-pad). Estabiliza a largura.

**Backward-compat (regra dura):** widget sem nenhum dos dois campos = comportamento
**idêntico ao atual** (auto-detecta decimais, cap 3; sem padding).

## Não-objetivos (YAGNI)

- Separador de milhar / locale.
- Dígitos significativos (precision).
- Config global de site (é por widget).
- Truncar/limitar dígitos inteiros (só padding mínimo; nunca corta valor real).

## Design

### 1. Schema — `kpiOptions` ([schema.ts](../../../frontend/src/lib/layout/schema.ts))

Adicionar 2 campos ao `z.object` de `kpiOptions`, seguindo o padrão `.catch(undefined)`
já usado (degrada campo a campo, cobre ausente e inválido):

```ts
casasDecimais: z.number().int().min(0).max(6).optional().catch(undefined),
digitosInteiros: z.number().int().min(1).max(12).optional().catch(undefined),
```

Sem novo `.refine` — os dois campos são independentes entre si e dos limites.

### 2. Helper de formatação — `formatKpi`

Função **pura**, exportada de um módulo próprio (ex. `frontend/src/lib/kpiFormat.ts`)
para ser testável isolada e reutilizada pelo widget:

```ts
export function autoCasas(value: number): number   // lógica atual (cap 3)
export function formatKpi(
  value: number,
  opts: { casasDecimais?: number; digitosInteiros?: number },
): string
```

Comportamento:

1. `decimais = opts.casasDecimais ?? autoCasas(value)`
2. `s = value.toFixed(decimais)` (arredonda; produz também o sinal `-`)
3. Se `digitosInteiros` definido: separar sinal, separar parte inteira da fração,
   zero-pad **só a parte inteira** ao mínimo `digitosInteiros`, recompor
   `sinal + inteiroPad + (fração ? '.'+fração : '')`.

`autoCasas` extrai a expressão atual de KpiWidget.tsx:56 sem mudança de semântica:
inteiro → 0; senão `min(len(fração), 3)`.

Exemplos:

| value  | casasDecimais | digitosInteiros | saída     |
|--------|---------------|-----------------|-----------|
| 19.063 | —             | —               | `19.063`  (auto) |
| 19.063 | 2             | —               | `19.06`   |
| 19.063 | 2             | 3               | `019.06`  |
| 5.1    | 1             | 3               | `005.1`   |
| -5.1   | 1             | 3               | `-005.1`  |
| 130    | 0             | —               | `130`     |
| 130    | 0             | 5               | `00130`   |

### 3. KpiWidget ([KpiWidget.tsx](../../../frontend/src/components/widgets/KpiWidget.tsx))

- Aceitar props novas: `casasDecimais?: number`, `digitosInteiros?: number`.
- Substituir linhas 56-57 por `formatKpi`:
  - `displayValue = animated != null ? formatKpi(animated, opts) : '—'`
- `animated` é o valor interpolado do count-up; formatar cada frame com `formatKpi`
  mantém o padding em todos os frames (largura estável → menos refit do `useFitText`).
- `useLayoutEffect` de refit permanece igual (depende de `displayValue.length`).

### 4. Registry ([registry.tsx](../../../frontend/src/lib/widgets/registry.tsx))

Onde `KpiWidget` é montado a partir de `options`, passar `casasDecimais` e
`digitosInteiros` (espelhando como `limiteMin`/`limiteMax`/`label` já são passados).

### 5. UI do popover ([WidgetConfigPopover.tsx](../../../frontend/src/components/WidgetConfigPopover.tsx))

No bloco `widget.type === 'kpi'`, após "Rótulo", 2 inputs `number`:

- **Dígitos inteiros (mín.)** — `min=1 max=12`, placeholder `"auto"`.
- **Casas decimais** — `min=0 max=6`, placeholder `"auto"`.

Padrão de escrita idêntico aos limites: `value ?? ''`, vazio → `setOption({ campo: undefined })`,
senão `Number(e.target.value)`. Sem validação de bloqueio (schema já degrada).

## Testes

- **`kpiFormat.test.ts`** (unit, foco principal): `autoCasas` (inteiro, 1-3 casas, cap 3);
  `formatKpi` para cada linha da tabela acima + negativo + fração vazia + padding menor
  que os dígitos existentes (no-op, não corta).
- **`schema` (existente ou novo caso):** backward-compat (options vazio → sem os campos),
  clamp/catch de valor inválido (ex. `casasDecimais: 99` ou string → undefined).
- **`KpiWidget.test.tsx`:** já existe; adicionar caso render com `digitosInteiros`/`casasDecimais`
  garantindo texto formatado; caso sem config = comportamento atual (não regride).

## Riscos

- Count-up: `formatKpi` roda por frame — barato (string ops), sem risco de perf.
- Refit: padding torna largura estável; efeito só positivo.
- Backward-compat garantido pelo `??` (ausente → `autoCasas`).
