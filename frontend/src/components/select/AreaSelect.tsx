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
