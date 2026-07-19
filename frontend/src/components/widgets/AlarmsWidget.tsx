import { useAlarms, useSensors } from '../../lib/queries'
import { AlarmPanel } from '../AlarmPanel'

// Container adaptador: mesma composicao de alarmes+nomes de area da
// DashboardPage, mas com escopo restrito a uma area quando scope==='area'
// (uso em dashboards de site menores, focados numa unica sala).
export function AlarmsWidget({ scope, areaCode }: { scope: 'site' | 'area'; areaCode?: string }) {
  const alarmsQuery = useAlarms()
  const sensors = useSensors().data ?? []
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const all = alarmsQuery.data ?? []
  const alarms = scope === 'area' && areaCode ? all.filter((a) => a.area_code === areaCode) : all

  return <AlarmPanel alarms={alarms} areaNameByCode={areaNameByCode} onVerMais={() => {}} />
}
