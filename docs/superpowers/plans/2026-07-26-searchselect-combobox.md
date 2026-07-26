# SearchSelect — combobox pesquisável genérico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Componente genérico de seleção pesquisável (`SearchSelect<T>`) com filtro por digitação + modal "Pesquisar mais" multi-campo (Odoo-like), adotado nos selects de área/sensor do `WidgetConfigPopover`.

**Architecture:** Um `SearchSelect<T>` genérico (single/multi via Downshift) que opera sobre `items: T[]` + um `EntityConfig<T>`. Uma `SearchMoreDialog<T>` (modal-tabela) reusada por ambos os modos. Configs por entidade (`areaConfig`/`sensorConfig`) + wrappers finos (`AreaSelect`/`SensorSelect`) que buscam os dados via `useSensors()`. Nada de busca no servidor — tudo client-side.

**Tech Stack:** React 19, TypeScript, Downshift (novo), @floating-ui/react (já dep), Vitest + Testing Library.

## Global Constraints

- Componente genérico: `SearchSelect`/`SearchMoreDialog`/`types.ts` NÃO podem importar nada de área/sensor. Só `EntityConfig<T>` + `items`.
- Componente controlado: nunca guarda a seleção como fonte de verdade; reporta via `onChange` (mesma disciplina do `WidgetConfigPopover`).
- Busca 100% client-side (dados já em memória via `useSensors()`).
- Estilo AFR: usar tokens `var(--color-*)`, shell `.drawer-panel`/`drawer-backdrop` para a modal, chips iguais aos do `WidgetConfigPopover` (`rounded-full px-2.5 py-1 text-xs font-bold`).
- Adoção não muda o contrato de `binding`: continua gravando `areaCode` / `sensorCode` / `areaCodes`.
- Downshift: fixar major (`^9`) no `package.json`.
- Arquivos da família em `frontend/src/components/select/`. Testes ao lado (`*.test.tsx`), padrão do repo.
- Todos os comandos rodam de `frontend/`.

---

### Task 1: Dependência Downshift + tipos + configs de entidade

**Files:**
- Modify: `frontend/package.json` (add `downshift`)
- Create: `frontend/src/components/select/types.ts`
- Create: `frontend/src/components/select/entityConfigs.ts`
- Test: `frontend/src/components/select/entityConfigs.test.ts`

**Interfaces:**
- Produces:
  - `type EntityConfig<T> = { getId:(i:T)=>string; getLabel:(i:T)=>string; getSecondary?:(i:T)=>string; searchText:(i:T)=>string; columns:{header:string; cell:(i:T)=>React.ReactNode}[] }`
  - `type Area = SensorMeta['area']` (`{ area_code:string; name:string; category:string }`)
  - `deriveAreas(sensors: SensorMeta[]): Area[]` — dedup por `area_code`, ordenado por `name`.
  - `areaConfig: EntityConfig<Area>`, `sensorConfig: EntityConfig<SensorMeta>`.

- [ ] **Step 1: Instalar Downshift**

Run: `npm install downshift@^9`
Expected: `package.json` ganha `"downshift": "^9.x"` em dependencies; `package-lock.json` atualizado.

- [ ] **Step 2: Criar o tipo genérico** (`frontend/src/components/select/types.ts`)

```ts
import type { ReactNode } from 'react'

// Config que torna o SearchSelect genérico: descreve COMO ler/mostrar/buscar
// uma entidade qualquer, sem o componente conhecer "área"/"sensor".
export type EntityConfig<T> = {
  getId: (item: T) => string
  getLabel: (item: T) => string            // rótulo primário (nome)
  getSecondary?: (item: T) => string       // sub-linha no dropdown
  searchText: (item: T) => string          // campos concatenados p/ busca da modal
  columns: { header: string; cell: (item: T) => ReactNode }[] // colunas da modal-tabela
}
```

- [ ] **Step 3: Escrever o teste falho** (`frontend/src/components/select/entityConfigs.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { deriveAreas, areaConfig, sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const s = (over: Partial<SensorMeta> = {}): SensorMeta => ({
  sensor_code: 'S1', name: 'Sensor Um', unidade: '°C',
  protocolo_origem: '4-20ma', measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: 'A1', name: 'Expurgo', category: 'critica' },
  ...over,
})

describe('deriveAreas', () => {
  it('dedup por area_code e ordena por name', () => {
    const areas = deriveAreas([
      s({ sensor_code: 'S1', area: { area_code: 'A2', name: 'Preparo', category: 'c' } }),
      s({ sensor_code: 'S2', area: { area_code: 'A1', name: 'Arsenal', category: 'c' } }),
      s({ sensor_code: 'S3', area: { area_code: 'A2', name: 'Preparo', category: 'c' } }),
    ])
    expect(areas.map((a) => a.area_code)).toEqual(['A1', 'A2']) // Arsenal < Preparo
  })
})

describe('sensorConfig', () => {
  it('searchText casa em nome, código, área e tipo (multi-campo)', () => {
    const t = sensorConfig.searchText(s()).toLowerCase()
    expect(t).toContain('sensor um')
    expect(t).toContain('s1')
    expect(t).toContain('expurgo')
    expect(t).toContain('temperatura')
  })
  it('colunas incluem Nome, Código, Área, Tipo, Unidade', () => {
    expect(sensorConfig.columns.map((c) => c.header)).toEqual(['Nome', 'Código', 'Área', 'Tipo', 'Unidade'])
  })
  it('getId/getLabel usam sensor_code/name', () => {
    expect(sensorConfig.getId(s())).toBe('S1')
    expect(sensorConfig.getLabel(s())).toBe('Sensor Um')
  })
})

describe('areaConfig', () => {
  it('searchText casa em nome, código e categoria', () => {
    const a = { area_code: 'A1', name: 'Expurgo', category: 'critica' }
    const t = areaConfig.searchText(a).toLowerCase()
    expect(t).toContain('expurgo')
    expect(t).toContain('a1')
    expect(t).toContain('critica')
  })
  it('colunas incluem Nome, Código, Categoria', () => {
    expect(areaConfig.columns.map((c) => c.header)).toEqual(['Nome', 'Código', 'Categoria'])
  })
})
```

- [ ] **Step 4: Rodar o teste — deve falhar**

Run: `npx vitest run src/components/select/entityConfigs.test.ts`
Expected: FAIL — `Cannot find module './entityConfigs'`.

- [ ] **Step 5: Implementar** (`frontend/src/components/select/entityConfigs.ts`)

```ts
import type { SensorMeta } from '../../lib/types'
import type { EntityConfig } from './types'

export type Area = SensorMeta['area'] // { area_code, name, category }

// Áreas não vêm numa lista própria — derivam dos sensores. Dedup por area_code,
// ordenado por nome (mesma resolução usada no WidgetConfigPopover).
export function deriveAreas(sensors: SensorMeta[]): Area[] {
  const byCode = new Map<string, Area>(sensors.map((s) => [s.area.area_code, s.area]))
  return Array.from(byCode.values()).sort((a, b) => a.name.localeCompare(b.name))
}

export const areaConfig: EntityConfig<Area> = {
  getId: (a) => a.area_code,
  getLabel: (a) => a.name,
  getSecondary: (a) => `${a.area_code} · ${a.category}`,
  searchText: (a) => `${a.name} ${a.area_code} ${a.category}`,
  columns: [
    { header: 'Nome', cell: (a) => a.name },
    { header: 'Código', cell: (a) => a.area_code },
    { header: 'Categoria', cell: (a) => a.category },
  ],
}

export const sensorConfig: EntityConfig<SensorMeta> = {
  getId: (s) => s.sensor_code,
  getLabel: (s) => s.name,
  getSecondary: (s) => `${s.sensor_code} · ${s.area.name} · ${s.measurement_type.name}`,
  searchText: (s) =>
    `${s.name} ${s.sensor_code} ${s.area.name} ${s.measurement_type.name} ${s.unidade} ${s.protocolo_origem}`,
  columns: [
    { header: 'Nome', cell: (s) => s.name },
    { header: 'Código', cell: (s) => s.sensor_code },
    { header: 'Área', cell: (s) => s.area.name },
    { header: 'Tipo', cell: (s) => s.measurement_type.name },
    { header: 'Unidade', cell: (s) => s.unidade },
  ],
}
```

- [ ] **Step 6: Rodar o teste — deve passar**

Run: `npx vitest run src/components/select/entityConfigs.test.ts`
Expected: PASS (todos).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/select/types.ts frontend/src/components/select/entityConfigs.ts frontend/src/components/select/entityConfigs.test.ts
git commit -m "feat(select): tipo EntityConfig + configs área/sensor + Downshift dep"
```

---

### Task 2: `SearchMoreDialog` — modal-tabela multi-campo

**Files:**
- Create: `frontend/src/components/select/SearchMoreDialog.tsx`
- Test: `frontend/src/components/select/SearchMoreDialog.test.tsx`

**Interfaces:**
- Consumes: `EntityConfig<T>` (Task 1).
- Produces:
  - `function SearchMoreDialog<T>(props): JSX.Element`
  - Props: `{ items: T[]; config: EntityConfig<T>; multiple: boolean; initialSelectedIds: string[]; onConfirm: (ids: string[]) => void; onClose: () => void; title?: string }`
  - Semântica: single → clicar linha chama `onConfirm([id])` e fecha; multi → checkbox por linha, botão "Confirmar" chama `onConfirm(idsMarcados)`, "Cancelar"/Esc/backdrop chamam `onClose`.

- [ ] **Step 1: Escrever o teste falho** (`frontend/src/components/select/SearchMoreDialog.test.tsx`)

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchMoreDialog } from './SearchMoreDialog'
import { sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const mk = (code: string, name: string, area: string): SensorMeta => ({
  sensor_code: code, name, unidade: '°C', protocolo_origem: '4-20ma',
  measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: area, name: area, category: 'c' },
})
const items = [mk('S1', 'Autoclave 1', 'Expurgo'), mk('S2', 'Camara Fria', 'Arsenal')]

describe('SearchMoreDialog', () => {
  it('renderiza tabela com as colunas do config (role=dialog)', () => {
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Autoclave 1')).toBeInTheDocument()
    // header de coluna
    expect(screen.getByRole('columnheader', { name: 'Área' })).toBeInTheDocument()
  })

  it('busca casa em campo secundário (área), não só no nome', async () => {
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'arsenal' } })
    expect(screen.queryByText('Autoclave 1')).toBeNull()
    expect(screen.getByText('Camara Fria')).toBeInTheDocument()
  })

  it('single: clicar na linha chama onConfirm([id]) e onClose', async () => {
    const onConfirm = vi.fn(); const onClose = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={onConfirm} onClose={onClose} />)
    await userEvent.click(screen.getByText('Camara Fria'))
    expect(onConfirm).toHaveBeenCalledWith(['S2'])
    expect(onClose).toHaveBeenCalled()
  })

  it('multi: marca checkboxes e Confirmar chama onConfirm com o conjunto', async () => {
    const onConfirm = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple initialSelectedIds={['S1']} onConfirm={onConfirm} onClose={vi.fn()} />)
    // S1 já marcado; marca S2
    await userEvent.click(screen.getByRole('checkbox', { name: /Camara Fria/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(onConfirm).toHaveBeenCalledWith(['S1', 'S2'])
  })

  it('Esc fecha só a modal (onClose)', async () => {
    const onClose = vi.fn()
    render(<SearchMoreDialog items={items} config={sensorConfig} multiple={false} initialSelectedIds={[]} onConfirm={vi.fn()} onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `npx vitest run src/components/select/SearchMoreDialog.test.tsx`
Expected: FAIL — `Cannot find module './SearchMoreDialog'`.

- [ ] **Step 3: Implementar** (`frontend/src/components/select/SearchMoreDialog.tsx`)

```tsx
import { useMemo, useState } from 'react'
import { useFloating, useDismiss, useInteractions, FloatingFocusManager, FloatingPortal, FloatingOverlay } from '@floating-ui/react'
import type { EntityConfig } from './types'

// Modal-tabela "Pesquisar mais" (Odoo-like). Genérica: só sabe de EntityConfig.
// Abre SOBRE o contexto atual (inclusive sobre o WidgetConfigDrawer) — shell
// igual ao SensorDetailDrawer: FloatingOverlay ancestral + FocusManager modal.
// Fechar (Esc/backdrop/✕/Cancelar) chama onClose e NÃO afeta o drawer por baixo.
export function SearchMoreDialog<T>({
  items, config, multiple, initialSelectedIds, onConfirm, onClose, title,
}: {
  items: T[]
  config: EntityConfig<T>
  multiple: boolean
  initialSelectedIds: string[]
  onConfirm: (ids: string[]) => void
  onClose: () => void
  title?: string
}) {
  const [query, setQuery] = useState('')
  const [marked, setMarked] = useState<string[]>(initialSelectedIds)

  const { context, refs } = useFloating({ open: true, onOpenChange: (o) => { if (!o) onClose() } })
  const dismiss = useDismiss(context, { outsidePress: true, escapeKey: true })
  const { getFloatingProps } = useInteractions([dismiss])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((it) => config.searchText(it).toLowerCase().includes(q))
  }, [items, config, query])

  function toggle(id: string) {
    setMarked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  }

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className="z-[60] drawer-backdrop" style={{ background: 'rgb(0 0 0 / 0.5)' }} data-testid="search-more-backdrop">
        <FloatingFocusManager context={context}>
          <div
            ref={refs.setFloating}
            role="dialog"
            aria-modal="true"
            aria-label={title ?? 'Pesquisar'}
            className="fixed left-1/2 top-1/2 z-[61] flex max-h-[80vh] w-[min(720px,94vw)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg"
            style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-menu)' }}
            {...getFloatingProps()}
          >
            <div className="flex items-center gap-2 p-3">
              <input
                aria-label="Buscar"
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar em todos os campos…"
                className="w-full rounded border px-2 py-1 text-sm"
                style={{ borderColor: 'var(--color-muted)' }}
              />
              <button type="button" aria-label="Fechar" onClick={onClose} className="min-h-9 min-w-9 rounded text-lg" style={{ color: 'var(--color-muted)' }}>✕</button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-3">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    {multiple && <th className="w-8" />}
                    {config.columns.map((c) => <th key={c.header} scope="col" className="px-2 py-1 font-semibold" style={{ color: 'var(--color-muted)' }}>{c.header}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr><td colSpan={config.columns.length + (multiple ? 1 : 0)} className="px-2 py-3 text-center" style={{ color: 'var(--color-muted)' }}>Nada encontrado</td></tr>
                  )}
                  {filtered.map((it) => {
                    const id = config.getId(it)
                    return (
                      <tr
                        key={id}
                        className="cursor-pointer hover:bg-black/10"
                        onClick={multiple ? undefined : () => { onConfirm([id]); onClose() }}
                      >
                        {multiple && (
                          <td className="px-2 py-1">
                            <input
                              type="checkbox"
                              aria-label={config.getLabel(it)}
                              checked={marked.includes(id)}
                              onChange={() => toggle(id)}
                            />
                          </td>
                        )}
                        {config.columns.map((c, i) => <td key={i} className="px-2 py-1">{c.cell(it)}</td>)}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {multiple && (
              <div className="flex justify-end gap-2 p-3">
                <button type="button" onClick={onClose} className="rounded border px-3 py-1 text-sm">Cancelar</button>
                <button type="button" onClick={() => { onConfirm(marked); onClose() }} className="rounded px-3 py-1 text-sm font-bold text-white" style={{ background: 'var(--color-primary)' }}>Confirmar</button>
              </div>
            )}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
```

- [ ] **Step 4: Rodar — deve passar**

Run: `npx vitest run src/components/select/SearchMoreDialog.test.tsx`
Expected: PASS. Se o teste multi de checkbox falhar por ordem dos ids, ajustar a asserção para `expect(onConfirm.mock.calls[0][0].sort()).toEqual(['S1','S2'])` (ordem não importa no conjunto).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/select/SearchMoreDialog.tsx frontend/src/components/select/SearchMoreDialog.test.tsx
git commit -m "feat(select): SearchMoreDialog modal-tabela multi-campo"
```

---

### Task 3: `SearchSelect` — modo single (combobox)

**Files:**
- Create: `frontend/src/components/select/SearchSelect.tsx`
- Test: `frontend/src/components/select/SearchSelect.single.test.tsx`

**Interfaces:**
- Consumes: `EntityConfig<T>` (Task 1), `SearchMoreDialog` (Task 2).
- Produces:
  - `function SearchSelect<T>(props: SingleProps<T> | MultiProps<T>): JSX.Element`
  - `type SingleProps<T> = { items:T[]; config:EntityConfig<T>; label?:string; placeholder?:string; multiple?:false; value:string|null; onChange:(id:string|null)=>void }`
  - `type MultiProps<T> = { items:T[]; config:EntityConfig<T>; label?:string; placeholder?:string; multiple:true; value:string[]; onChange:(ids:string[])=>void }`
  - Task 3 implementa SÓ o caminho single; o multi (`multiple:true`) entra na Task 4. Definir os dois tipos já agora (a união é a interface pública), mas o corpo multi pode ser um `return null`/TODO **só** se a Task 4 vier logo em seguida — preferível implementar single e deixar multi lançar `throw new Error('multi na Task 4')` para não fingir teste passando. **Na prática: escreva a união e ramifique `if (props.multiple)`; o galho multi fica mínimo até a Task 4.**

- [ ] **Step 1: Escrever o teste falho** (`frontend/src/components/select/SearchSelect.single.test.tsx`)

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchSelect } from './SearchSelect'
import { sensorConfig } from './entityConfigs'
import type { SensorMeta } from '../../lib/types'

const mk = (code: string, name: string): SensorMeta => ({
  sensor_code: code, name, unidade: '°C', protocolo_origem: '4-20ma',
  measurement_type: { code: 'temp', name: 'Temperatura' },
  area: { area_code: 'A1', name: 'Expurgo', category: 'c' },
})
const items = [mk('S1', 'Autoclave 1'), mk('S2', 'Camara Fria'), mk('S3', 'Lavadora')]

describe('SearchSelect single', () => {
  it('mostra o label do item selecionado', () => {
    render(<SearchSelect items={items} config={sensorConfig} value="S2" onChange={vi.fn()} label="Sensor" />)
    expect(screen.getByDisplayValue('Camara Fria')).toBeInTheDocument()
  })

  it('digitar filtra as opções pelo nome', async () => {
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.type(screen.getByRole('combobox'), 'lav')
    expect(screen.getByText('Lavadora')).toBeInTheDocument()
    expect(screen.queryByText('Autoclave 1')).toBeNull()
  })

  it('escolher uma opção chama onChange com o id', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByText('Autoclave 1'))
    expect(onChange).toHaveBeenCalledWith('S1')
  })

  it('limpar (×) chama onChange(null)', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value="S1" onChange={onChange} />)
    await userEvent.click(screen.getByLabelText('Limpar seleção'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('id sem item correspondente cai no próprio id como fallback (sem crash)', () => {
    render(<SearchSelect items={items} config={sensorConfig} value="SX" onChange={vi.fn()} />)
    expect(screen.getByDisplayValue('SX')).toBeInTheDocument()
  })

  it('abre a modal Pesquisar mais e selecionar lá chama onChange', async () => {
    const onChange = vi.fn()
    render(<SearchSelect items={items} config={sensorConfig} value={null} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('button', { name: /Pesquisar mais/ }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Camara Fria'))
    expect(onChange).toHaveBeenCalledWith('S2')
  })
})
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `npx vitest run src/components/select/SearchSelect.single.test.tsx`
Expected: FAIL — `Cannot find module './SearchSelect'`.

- [ ] **Step 3: Implementar** (`frontend/src/components/select/SearchSelect.tsx`)

```tsx
import { useMemo, useState } from 'react'
import { useCombobox } from 'downshift'
import type { EntityConfig } from './types'
import { SearchMoreDialog } from './SearchMoreDialog'

type Base<T> = { items: T[]; config: EntityConfig<T>; label?: string; placeholder?: string }
export type SingleProps<T> = Base<T> & { multiple?: false; value: string | null; onChange: (id: string | null) => void }
export type MultiProps<T> = Base<T> & { multiple: true; value: string[]; onChange: (ids: string[]) => void }

export function SearchSelect<T>(props: SingleProps<T> | MultiProps<T>) {
  if (props.multiple) return <MultiSelect {...props} />
  return <SingleSelect {...props} />
}

const PESQUISAR_MAIS = '__pesquisar_mais__'

function SingleSelect<T>({ items, config, value, onChange, label, placeholder }: SingleProps<T>) {
  const [input, setInput] = useState('')
  const [dialog, setDialog] = useState(false)

  const selected = value == null ? null : items.find((i) => config.getId(i) === value) ?? null
  const selectedLabel = selected ? config.getLabel(selected) : value ?? '' // fallback: id cru

  const filtered = useMemo(() => {
    const q = input.trim().toLowerCase()
    if (!q) return items
    return items.filter((i) => config.getLabel(i).toLowerCase().includes(q))
  }, [items, config, input])

  const {
    isOpen, getMenuProps, getInputProps, getItemProps, highlightedIndex, openMenu,
  } = useCombobox({
    items: filtered,
    inputValue: isOpenSafe(input, selectedLabel),
    itemToString: (i) => (i ? config.getLabel(i) : ''),
    onInputValueChange: ({ inputValue }) => setInput(inputValue ?? ''),
    onSelectedItemChange: ({ selectedItem }) => {
      if (selectedItem) onChange(config.getId(selectedItem))
    },
    selectedItem: selected,
  })

  return (
    <div className="relative">
      {label && <span className="block text-xs" style={{ color: 'var(--color-muted)' }}>{label}</span>}
      <div className="relative mt-1 flex items-center">
        <input
          {...getInputProps({ onFocus: () => openMenu() })}
          role="combobox"
          placeholder={placeholder ?? 'Selecionar…'}
          className="w-full rounded border px-2 py-1 pr-12 text-xs"
          style={{ borderColor: 'var(--color-muted)' }}
        />
        {value != null && (
          <button type="button" aria-label="Limpar seleção" onClick={() => { onChange(null); setInput('') }}
            className="absolute right-6 text-xs" style={{ color: 'var(--color-muted)' }}>×</button>
        )}
      </div>
      <ul {...getMenuProps()} className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded border text-xs ${isOpen ? '' : 'hidden'}`}
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-line)' }}>
        {isOpen && filtered.map((item, index) => (
          <li key={config.getId(item)} {...getItemProps({ item, index })}
            className={`cursor-pointer px-2 py-1 ${highlightedIndex === index ? 'bg-black/10' : ''}`}>
            <div>{config.getLabel(item)}</div>
            {config.getSecondary && <div style={{ color: 'var(--color-muted)' }}>{config.getSecondary(item)}</div>}
          </li>
        ))}
        {isOpen && (
          <li>
            <button type="button" onClick={() => setDialog(true)}
              className="w-full px-2 py-1 text-left font-semibold" style={{ color: 'var(--color-primary)' }}>
              Pesquisar mais…
            </button>
          </li>
        )}
      </ul>
      {dialog && (
        <SearchMoreDialog
          items={items} config={config} multiple={false}
          initialSelectedIds={value ? [value] : []}
          title={label ? `Pesquisar ${label}` : 'Pesquisar'}
          onConfirm={(ids) => onChange(ids[0] ?? null)}
          onClose={() => setDialog(false)}
        />
      )}
    </div>
  )
}

// Placeholder até a Task 4 (o galho multi é implementado lá).
function MultiSelect<T>(_props: MultiProps<T>) {
  throw new Error('SearchSelect multi: implementado na Task 4')
}

// inputValue controlado: quando o usuário NÃO está digitando (input vazio),
// mostra o label do selecionado; enquanto digita, mostra o que ele digitou.
function isOpenSafe(input: string, selectedLabel: string): string {
  return input === '' ? selectedLabel : input
}
```

- [ ] **Step 4: Rodar — deve passar**

Run: `npx vitest run src/components/select/SearchSelect.single.test.tsx`
Expected: PASS. Downshift + jsdom podem exigir ajuste fino nos handlers (ex.: `openMenu` no foco, `role="combobox"` já provido por `getInputProps`). Se algum teste de teclado/abrir divergir, ajustar via TDD mantendo o contrato dos testes; NÃO enfraquecer as asserções de `onChange`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/select/SearchSelect.tsx frontend/src/components/select/SearchSelect.single.test.tsx
git commit -m "feat(select): SearchSelect modo single (combobox + Pesquisar mais)"
```

---

### Task 4: `SearchSelect` — modo multi (chips)

**Files:**
- Modify: `frontend/src/components/select/SearchSelect.tsx` (implementar `MultiSelect`)
- Test: `frontend/src/components/select/SearchSelect.multi.test.tsx`

**Interfaces:**
- Consumes: tipos/`SingleSelect`/`SearchMoreDialog` já definidos na Task 3.
- Produces: `MultiSelect<T>` funcional; `SearchSelect` com `multiple` renderiza chips + dropdown que alterna seleção.

- [ ] **Step 1: Escrever o teste falho** (`frontend/src/components/select/SearchSelect.multi.test.tsx`)

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchSelect } from './SearchSelect'
import { areaConfig, type Area } from './entityConfigs'

const areas: Area[] = [
  { area_code: 'A1', name: 'Expurgo', category: 'c' },
  { area_code: 'A2', name: 'Preparo', category: 'c' },
  { area_code: 'A3', name: 'Arsenal', category: 'c' },
]

describe('SearchSelect multi', () => {
  it('mostra chips dos selecionados', () => {
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1', 'A3']} onChange={vi.fn()} />)
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Arsenal')).toBeInTheDocument()
  })

  it('escolher no dropdown adiciona o id via onChange', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByText('Preparo'))
    expect(onChange).toHaveBeenCalledWith(['A1', 'A2'])
  })

  it('remover chip chama onChange sem o id', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1', 'A3']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Remover Expurgo' }))
    expect(onChange).toHaveBeenCalledWith(['A3'])
  })

  it('Pesquisar mais em multi confirma o conjunto marcado', async () => {
    const onChange = vi.fn()
    render(<SearchSelect multiple items={areas} config={areaConfig} value={['A1']} onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('button', { name: /Pesquisar mais/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Arsenal' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(onChange).toHaveBeenCalledWith(['A1', 'A3'])
  })
})
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `npx vitest run src/components/select/SearchSelect.multi.test.tsx`
Expected: FAIL — `MultiSelect: implementado na Task 4` (throw) ou asserções não atendidas.

- [ ] **Step 3: Implementar** — substituir `MultiSelect` em `SearchSelect.tsx`

```tsx
import { useMultipleSelection, useCombobox } from 'downshift'
// (ajustar o import do topo: `import { useCombobox, useMultipleSelection } from 'downshift'`)

function MultiSelect<T>({ items, config, value, onChange, label, placeholder }: MultiProps<T>) {
  const [input, setInput] = useState('')
  const [dialog, setDialog] = useState(false)

  const selectedItems = value.map((id) => items.find((i) => config.getId(i) === id)).filter(Boolean) as T[]

  const filtered = useMemo(() => {
    const q = input.trim().toLowerCase()
    const base = items.filter((i) => !value.includes(config.getId(i)))
    if (!q) return base
    return base.filter((i) => config.getLabel(i).toLowerCase().includes(q))
  }, [items, config, value, input])

  const { getDropdownProps, removeSelectedItem } = useMultipleSelection<T>({
    selectedItems,
    onStateChange: ({ selectedItems: si, type }) => {
      // remoções via teclado (Backspace) do Downshift refletem no onChange
      if (
        type === useMultipleSelection.stateChangeTypes.SelectedItemKeyDownBackspace ||
        type === useMultipleSelection.stateChangeTypes.SelectedItemKeyDownDelete ||
        type === useMultipleSelection.stateChangeTypes.FunctionRemoveSelectedItem
      ) {
        onChange((si ?? []).map((i) => config.getId(i)))
      }
    },
  })

  const { isOpen, getMenuProps, getInputProps, getItemProps, highlightedIndex, openMenu } = useCombobox({
    items: filtered,
    inputValue: input,
    itemToString: (i) => (i ? config.getLabel(i) : ''),
    onInputValueChange: ({ inputValue }) => setInput(inputValue ?? ''),
    stateReducer: (state, { changes, type }) => {
      // manter aberto e limpar o texto após escolher, p/ facilitar múltipla adição
      if (type === useCombobox.stateChangeTypes.ItemClick || type === useCombobox.stateChangeTypes.InputKeyDownEnter) {
        return { ...changes, isOpen: true, inputValue: '' }
      }
      return changes
    },
    onSelectedItemChange: ({ selectedItem }) => {
      if (selectedItem) { onChange([...value, config.getId(selectedItem)]); setInput('') }
    },
    selectedItem: null,
  })

  return (
    <div className="relative">
      {label && <span className="block text-xs" style={{ color: 'var(--color-muted)' }}>{label}</span>}
      {selectedItems.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-1">
          {selectedItems.map((it) => {
            const id = config.getId(it)
            return (
              <span key={id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold"
                style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)' }}>
                {config.getLabel(it)}
                <button type="button" aria-label={`Remover ${config.getLabel(it)}`} className="leading-none"
                  onClick={() => onChange(value.filter((v) => v !== id))}>×</button>
              </span>
            )
          })}
        </div>
      )}
      <input
        {...getInputProps(getDropdownProps({ preventKeyAction: isOpen, onFocus: () => openMenu() }))}
        role="combobox"
        placeholder={placeholder ?? 'Adicionar…'}
        className="w-full rounded border px-2 py-1 text-xs"
        style={{ borderColor: 'var(--color-muted)' }}
      />
      <ul {...getMenuProps()} className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded border text-xs ${isOpen ? '' : 'hidden'}`}
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-line)' }}>
        {isOpen && filtered.map((item, index) => (
          <li key={config.getId(item)} {...getItemProps({ item, index })}
            className={`cursor-pointer px-2 py-1 ${highlightedIndex === index ? 'bg-black/10' : ''}`}>
            <div>{config.getLabel(item)}</div>
            {config.getSecondary && <div style={{ color: 'var(--color-muted)' }}>{config.getSecondary(item)}</div>}
          </li>
        ))}
        {isOpen && (
          <li>
            <button type="button" onClick={() => setDialog(true)}
              className="w-full px-2 py-1 text-left font-semibold" style={{ color: 'var(--color-primary)' }}>
              Pesquisar mais…
            </button>
          </li>
        )}
      </ul>
      {dialog && (
        <SearchMoreDialog
          items={items} config={config} multiple
          initialSelectedIds={value}
          title={label ? `Pesquisar ${label}` : 'Pesquisar'}
          onConfirm={(ids) => onChange(ids)}
          onClose={() => setDialog(false)}
        />
      )}
    </div>
  )
}
```

Também remover o `removeSelectedItem` não usado se o lint reclamar (usar `onChange(value.filter(...))` direto no chip, como acima).

- [ ] **Step 4: Rodar — deve passar**

Run: `npx vitest run src/components/select/SearchSelect.multi.test.tsx`
Expected: PASS. Ajustar interações Downshift via TDD se preciso, sem enfraquecer as asserções de `onChange`.

- [ ] **Step 5: Rodar os dois testes do SearchSelect**

Run: `npx vitest run src/components/select/`
Expected: PASS (entityConfigs + SearchMoreDialog + single + multi).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/select/SearchSelect.tsx frontend/src/components/select/SearchSelect.multi.test.tsx
git commit -m "feat(select): SearchSelect modo multi (chips + toggle)"
```

---

### Task 5: Wrappers `AreaSelect` / `SensorSelect`

**Files:**
- Create: `frontend/src/components/select/AreaSelect.tsx`
- Create: `frontend/src/components/select/SensorSelect.tsx`
- Test: `frontend/src/components/select/wrappers.test.tsx`

**Interfaces:**
- Consumes: `SearchSelect`, `areaConfig`/`sensorConfig`/`deriveAreas` (Task 1), `useSensors` (`src/lib/queries`).
- Produces:
  - `AreaSelect(props)` e `SensorSelect(props)` — mesma união de props do `SearchSelect` MENOS `items`/`config` (injetados). Ou seja: `{ label?; placeholder? } & ({ multiple?:false; value:string|null; onChange:(id:string|null)=>void } | { multiple:true; value:string[]; onChange:(ids:string[])=>void })`.

- [ ] **Step 1: Escrever o teste falho** (`frontend/src/components/select/wrappers.test.tsx`)

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AreaSelect } from './AreaSelect'
import { SensorSelect } from './SensorSelect'

vi.mock('../../lib/queries', () => ({
  useSensors: () => ({ data: [
    { sensor_code: 'S1', name: 'Autoclave 1', unidade: '°C', protocolo_origem: '4-20ma',
      measurement_type: { code: 'temp', name: 'Temperatura' }, area: { area_code: 'A1', name: 'Expurgo', category: 'c' } },
    { sensor_code: 'S2', name: 'Camara Fria', unidade: '°C', protocolo_origem: '4-20ma',
      measurement_type: { code: 'temp', name: 'Temperatura' }, area: { area_code: 'A2', name: 'Arsenal', category: 'c' } },
  ] }),
}))

describe('wrappers', () => {
  it('SensorSelect resolve o label do sensor via useSensors', () => {
    render(<SensorSelect value="S2" onChange={vi.fn()} label="Sensor" />)
    expect(screen.getByDisplayValue('Camara Fria')).toBeInTheDocument()
  })
  it('AreaSelect deriva áreas dos sensores e mostra o label da área', () => {
    render(<AreaSelect value="A1" onChange={vi.fn()} label="Área" />)
    expect(screen.getByDisplayValue('Expurgo')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `npx vitest run src/components/select/wrappers.test.tsx`
Expected: FAIL — módulos não existem.

- [ ] **Step 3: Implementar** (`AreaSelect.tsx`)

```tsx
import { useSensors } from '../../lib/queries'
import { SearchSelect } from './SearchSelect'
import { areaConfig, deriveAreas, type Area } from './entityConfigs'

type Common = { label?: string; placeholder?: string }
type Props = Common & (
  | { multiple?: false; value: string | null; onChange: (id: string | null) => void }
  | { multiple: true; value: string[]; onChange: (ids: string[]) => void }
)

// Wrapper: busca os dados (áreas derivadas dos sensores) e injeta areaConfig.
// A fonte de dados fica FORA do SearchSelect genérico.
export function AreaSelect(props: Props) {
  const areas: Area[] = deriveAreas(useSensors().data ?? [])
  return <SearchSelect items={areas} config={areaConfig} {...props} />
}
```

`SensorSelect.tsx`:

```tsx
import { useSensors } from '../../lib/queries'
import { SearchSelect } from './SearchSelect'
import { sensorConfig } from './entityConfigs'

type Common = { label?: string; placeholder?: string }
type Props = Common & (
  | { multiple?: false; value: string | null; onChange: (id: string | null) => void }
  | { multiple: true; value: string[]; onChange: (ids: string[]) => void }
)

export function SensorSelect(props: Props) {
  const sensors = useSensors().data ?? []
  return <SearchSelect items={sensors} config={sensorConfig} {...props} />
}
```

- [ ] **Step 4: Rodar — deve passar**

Run: `npx vitest run src/components/select/wrappers.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/select/AreaSelect.tsx frontend/src/components/select/SensorSelect.tsx frontend/src/components/select/wrappers.test.tsx
git commit -m "feat(select): wrappers AreaSelect/SensorSelect (dados via useSensors)"
```

---

### Task 6: Adotar no `WidgetConfigPopover`

**Files:**
- Modify: `frontend/src/components/WidgetConfigPopover.tsx`
- Modify: `frontend/src/components/WidgetConfigPopover.test.tsx`

**Interfaces:**
- Consumes: `AreaSelect`, `SensorSelect` (Task 5).
- Produces: `WidgetConfigPopover` sem `<select>` nativo p/ área/sensor; multi-área do alarms via `<AreaSelect multiple>`; contrato de `binding` inalterado.

- [ ] **Step 1: Ajustar os testes existentes** (`WidgetConfigPopover.test.tsx`)

Os testes atuais de área/sensor usam `<select>` (`getByLabelText('Sensor')` + `selectOptions`). Substituir pelos novos componentes. Exemplos a converter (manter as asserções de `onChange`/binding):

Sensor (era `selectOptions`):
```tsx
it('escolher sensor grava binding.sensorCode', async () => {
  const onChange = vi.fn()
  render(<WidgetConfigPopover widget={tsWidget} onChange={onChange} onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('combobox'))
  await userEvent.click(screen.getByText('Sensor Dois'))
  expect(onChange).toHaveBeenLastCalledWith({ ...tsWidget, binding: { ...tsWidget.binding, sensorCode: 'S2' } })
})
```

Multi-área (era dropdown "Adicionar área" + chips): manter os testes de `binding.areaCodes`, mas interagindo via o combobox do `AreaSelect`:
```tsx
it('escolher área no combobox grava binding.areaCodes', async () => {
  const onChange = vi.fn()
  render(<WidgetConfigPopover widget={{ ...alarmsWidget, options: { scope: 'area' } }} onChange={onChange} onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('combobox'))
  await userEvent.click(screen.getByText('Área Dois'))
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
    binding: expect.objectContaining({ areaCodes: ['A2'] }),
  }))
})
```

Remover os testes que casavam especificamente o `<select>`/"Adicionar área" antigo (`getByLabelText('Adicionar área')`), já que a UI mudou. Preservar os testes de resolução legada (`areaCode → areaCodes`), adaptando a interação.

- [ ] **Step 2: Rodar — deve falhar**

Run: `npx vitest run src/components/WidgetConfigPopover.test.tsx`
Expected: FAIL (UI antiga não existe mais / novos componentes ainda não plugados).

- [ ] **Step 3: Implementar a adoção** — em `WidgetConfigPopover.tsx`

Trocar o bloco `areaSelect` (needs==='area'):
```tsx
import { AreaSelect } from './select/AreaSelect'
import { SensorSelect } from './select/SensorSelect'
// ...
const areaSelect = (
  <AreaSelect
    label="Área"
    value={widget.binding.areaCode ?? null}
    onChange={(code) => onChange({ ...widget, binding: { ...widget.binding, areaCode: code ?? undefined } })}
  />
)
```

Trocar o select de sensor (needs==='sensor'):
```tsx
{needs === 'sensor' && (
  <SensorSelect
    label="Sensor"
    value={widget.binding.sensorCode ?? null}
    onChange={(code) => onChange({ ...widget, binding: { ...widget.binding, sensorCode: code ?? undefined } })}
  />
)}
```

Trocar `alarmsAreaSection` (multi-área) por:
```tsx
const alarmsAreaSection = (
  <AreaSelect
    multiple
    label="Áreas"
    value={areaCodesEfetivos}
    onChange={(codes) => onChange({ ...widget, binding: { ...widget.binding, areaCodes: codes } })}
  />
)
```
Manter `areaCodesEfetivos = widget.binding.areaCodes ?? (widget.binding.areaCode ? [widget.binding.areaCode] : [])` para o valor inicial (resolução legada). Remover o código agora morto: `areasDisponiveis`, `nomeArea`, e o JSX manual de dropdown/chips embutido em `alarmsAreaSection`.

- [ ] **Step 4: Rodar os testes do popover — deve passar**

Run: `npx vitest run src/components/WidgetConfigPopover.test.tsx`
Expected: PASS.

- [ ] **Step 5: Rodar suíte completa + typecheck do build**

Run: `npx vitest run && npx tsc -b`
Expected: todos os testes PASS; `tsc -b` exit 0. (Corrigir qualquer straggler de tipo — ex.: teste que passava prop removida — antes de commitar.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WidgetConfigPopover.tsx frontend/src/components/WidgetConfigPopover.test.tsx
git commit -m "feat(dashboard): WidgetConfigPopover usa SearchSelect (área/sensor/multi-área)"
```

---

## Self-Review (do plano)

- **Cobertura do spec:** genérico (Task 1-4) ✓; modal multi-campo (Task 2) ✓; single+multi (Task 3-4) ✓; wrappers/reuso futuro (Task 5) ✓; adoção nos 3 pontos (Task 6) ✓; busca client-side (Task 2/entityConfigs) ✓; bordas (id inexistente/sem match) cobertas em testes ✓.
- **Riscos conhecidos:** Downshift em jsdom pode exigir ajuste fino nos handlers (foco/abrir/teclado). Os testes fixam o CONTRATO (`onChange`, filtro, chips) — o implementer refina a fiação Downshift via TDD sem enfraquecer asserções. Modal-dentro-de-drawer: `z-[60/61]` acima do drawer (`z-40/50`); validar layering na verificação visual.
- **Consistência de tipos:** `EntityConfig<T>` idêntico em types.ts e usos; `Area = SensorMeta['area']`; união `SingleProps|MultiProps` idêntica em SearchSelect e nos wrappers.
- **Verificação visual (pós-implementação, fora das tasks):** subir mock server (`vite --mode mock`), abrir editor, ⚙ → combobox → Pesquisar mais; screenshot claro/escuro (mesmo harness da feature anterior).
