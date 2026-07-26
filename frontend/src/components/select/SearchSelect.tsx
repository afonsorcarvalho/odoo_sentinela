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

function SingleSelect<T>({ items, config, value, onChange, label, placeholder }: SingleProps<T>) {
  const [input, setInput] = useState('')
  const [dialog, setDialog] = useState(false)

  const selected = value == null ? null : items.find((i) => config.getId(i) === value) ?? null
  const selectedLabel = selected ? config.getLabel(selected) : value ?? '' // fallback: id cru

  const filtered = useMemo(() => {
    const q = input.trim().toLowerCase()
    if (!q) return items
    return items.filter((i) => matchesWordStart(config.getLabel(i), q))
  }, [items, config, input])

  const {
    isOpen, getMenuProps, getInputProps, getItemProps, highlightedIndex,
  } = useCombobox({
    items: filtered,
    inputValue: input === '' ? selectedLabel : input,
    itemToString: (i) => (i ? config.getLabel(i) : ''),
    onInputValueChange: ({ inputValue, type }) => {
      // Ignora o eco de "inputValue" que o Downshift dispara ao trocar o
      // selectedItem (ItemClick) — senão isso reabre "input" com o label
      // escolhido e o próximo render recalcula inputValue errado.
      if (type === useCombobox.stateChangeTypes.ItemClick) return
      setInput(inputValue ?? '')
    },
    onSelectedItemChange: ({ selectedItem }) => {
      if (selectedItem) onChange(config.getId(selectedItem))
      setInput('')
    },
    selectedItem: selected,
  })

  return (
    <div className="relative">
      {label && <span className="block text-xs" style={{ color: 'var(--color-muted)' }}>{label}</span>}
      <div className="relative mt-1 flex items-center">
        <input
          {...getInputProps()}
          placeholder={placeholder ?? 'Selecionar…'}
          className="w-full rounded border px-2 py-1 pr-12 text-xs"
          style={{ borderColor: 'var(--color-muted)' }}
        />
        {value != null && (
          <button type="button" aria-label="Limpar seleção" onClick={() => { onChange(null); setInput('') }}
            className="absolute right-6 text-xs" style={{ color: 'var(--color-muted)' }}>×</button>
        )}
      </div>
      {/* Enquanto a modal "Pesquisar mais" está aberta, o dropdown fica
          escondido — senão itens com o mesmo label (ex.: "Camara Fria")
          existiriam duplicados no DOM (dropdown + tabela da modal). */}
      <ul {...getMenuProps()} className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded border text-xs ${isOpen && !dialog ? '' : 'hidden'}`}
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-line)' }}>
        {isOpen && !dialog && filtered.map((item, index) => (
          <li key={config.getId(item)} {...getItemProps({ item, index })}
            className={`cursor-pointer px-2 py-1 ${highlightedIndex === index ? 'bg-black/10' : ''}`}>
            <div>{config.getLabel(item)}</div>
            {config.getSecondary && <div style={{ color: 'var(--color-muted)' }}>{config.getSecondary(item)}</div>}
          </li>
        ))}
        {isOpen && !dialog && (
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
function MultiSelect<T>(_props: MultiProps<T>): never {
  throw new Error('SearchSelect multi: implementado na Task 4')
}

// Filtro do dropdown: casa por início de palavra (não substring qualquer),
// senão "lav" também acertaria "Autoclave" (contém "lav" no meio) além de
// "Lavadora" — ruído que a busca por digitação não deve mostrar.
function matchesWordStart(label: string, query: string): boolean {
  return label
    .toLowerCase()
    .split(/\s+/)
    .some((word) => word.startsWith(query))
}
