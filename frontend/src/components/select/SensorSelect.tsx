import { useSensors } from '../../lib/queries'
import { SearchSelect } from './SearchSelect'
import { sensorConfig } from './entityConfigs'

type Common = { label?: string; placeholder?: string }
type Props = Common & (
  | { multiple?: false; value: string | null; onChange: (id: string | null) => void }
  | { multiple: true; value: string[]; onChange: (ids: string[]) => void }
)

// Wrapper: busca os sensores via useSensors e injeta sensorConfig.
export function SensorSelect(props: Props) {
  const sensors = useSensors().data ?? []
  return <SearchSelect items={sensors} config={sensorConfig} {...props} />
}
