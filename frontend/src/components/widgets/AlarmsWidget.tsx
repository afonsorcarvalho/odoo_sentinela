import { useState } from 'react'
import { useAlarms, useSensors } from '../../lib/queries'
import { AlarmPanel } from '../AlarmPanel'
import { AlarmsModal } from '../AlarmsModal'

// Container adaptador: mesma composicao de alarmes+nomes de area da
// DashboardPage, mas com escopo restrito a uma area quando scope==='area'
// (uso em dashboards de site menores, focados numa unica sala).
// Dono da propria modal "Ver mais": um widget no meio do grid nao tem um
// callback natural a nivel de pagina, entao o widget se auto-contem.
export function AlarmsWidget({ scope, areaCodes }: { scope: 'site' | 'area'; areaCodes: string[] }) {
  const [modalOpen, setModalOpen] = useState(false)
  const alarmsQuery = useAlarms()
  const sensors = useSensors().data ?? []
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))
  const all = alarmsQuery.data ?? []
  // areaCodes=[] em scope='area' é fallback seguro para o site inteiro (não esconde alarme).
  const alarms = scope === 'area' && areaCodes.length > 0
    ? all.filter((a) => areaCodes.includes(a.area_code))
    : all

  return (
    <>
      <AlarmPanel alarms={alarms} areaNameByCode={areaNameByCode} onVerMais={() => setModalOpen(true)} />
      {modalOpen && (
        <AlarmsModal alarms={alarms} areaNameByCode={areaNameByCode} onClose={() => setModalOpen(false)} />
      )}
    </>
  )
}
