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
