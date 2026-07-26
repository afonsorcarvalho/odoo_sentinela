import { useMemo, useState } from 'react'
import { useCombobox, useMultipleSelection } from 'downshift'
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
    return items.filter((i) => matchesInline(config.getLabel(i), q))
  }, [items, config, input])

  const {
    isOpen, getMenuProps, getInputProps, getItemProps, highlightedIndex, getLabelProps,
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
      {/* label sempre renderizado via getLabelProps: o getInputProps do Downshift
          injeta aria-labelledby apontando p/ este id; sem o elemento, o input
          ficava sem nome acessível. Sem texto visível, fica sr-only. */}
      <label {...getLabelProps()} className={label ? 'block text-xs' : 'sr-only'} style={{ color: 'var(--color-muted)' }}>
        {label ?? 'Selecionar'}
      </label>
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

function MultiSelect<T>({ items, config, value, onChange, label, placeholder }: MultiProps<T>) {
  const [input, setInput] = useState('')
  const [dialog, setDialog] = useState(false)

  const selectedItems = value.map((id) => items.find((i) => config.getId(i) === id)).filter(Boolean) as T[]

  const filtered = useMemo(() => {
    const q = input.trim().toLowerCase()
    const base = items.filter((i) => !value.includes(config.getId(i)))
    if (!q) return base
    return base.filter((i) => matchesInline(config.getLabel(i), q))
  }, [items, config, value, input])

  const { getDropdownProps } = useMultipleSelection<T>({
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

  const { isOpen, getMenuProps, getInputProps, getItemProps, highlightedIndex, getLabelProps } = useCombobox({
    items: filtered,
    inputValue: input,
    itemToString: (i) => (i ? config.getLabel(i) : ''),
    onInputValueChange: ({ inputValue }) => setInput(inputValue ?? ''),
    stateReducer: (_state, { changes, type }) => {
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
      <label {...getLabelProps()} className={label ? 'block text-xs' : 'sr-only'} style={{ color: 'var(--color-muted)' }}>
        {label ?? 'Adicionar'}
      </label>
      {value.length > 0 && (
        <div className="mb-1 mt-1 flex flex-wrap gap-1">
          {/* Itera VALUE (não selectedItems): um id órfão — que não existe mais
              em items — ainda ganha chip (com o id cru como rótulo), então dá p/
              ver e remover; senão ficaria preso no binding, invisível. */}
          {value.map((id) => {
            const it = items.find((i) => config.getId(i) === id)
            const txt = it ? config.getLabel(it) : id
            return (
              <span key={id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold"
                style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)' }}>
                {txt}
                <button type="button" aria-label={`Remover ${txt}`} className="leading-none"
                  onClick={() => onChange(value.filter((v) => v !== id))}>×</button>
              </span>
            )
          })}
        </div>
      )}
      <input
        {...getInputProps(getDropdownProps({ preventKeyAction: isOpen }))}
        placeholder={placeholder ?? 'Adicionar…'}
        className="w-full rounded border px-2 py-1 text-xs"
        style={{ borderColor: 'var(--color-muted)' }}
      />
      {/* Enquanto a modal "Pesquisar mais" está aberta, o dropdown fica
          escondido — mesma razão do modo single (evitar duplicados no DOM). */}
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

// Filtro do dropdown: substring em qualquer posição do rótulo (mais permissivo,
// UX padrão de combobox). `query` já vem trim+lowercase do chamador.
function matchesInline(label: string, query: string): boolean {
  return label.toLowerCase().includes(query)
}
