import { useMemo, useState } from 'react'
import { useAlarms, useSensors } from '../../lib/queries'
import { AlarmPanel } from '../AlarmPanel'
import { AlarmsModal } from '../AlarmsModal'

// Container adaptador: mesma composicao de alarmes+nomes de area da
// DashboardPage, mas com escopo restrito a uma area quando scope==='area'
// (uso em dashboards de site menores, focados numa unica sala).
// Dono da propria modal "Ver mais": um widget no meio do grid nao tem um
// callback natural a nivel de pagina, entao o widget se auto-contem.
//
// Filtro de areas ao vivo (ver docs/superpowers/specs/2026-07-20-alarme-filtro-area-runtime-design.md):
// a config (scope/areaCodes) define o DEFAULT do filtro; o operador pode
// ligar/desligar qualquer area do site ao vivo, via chips. E estado de
// SESSAO (useState, nao persiste no blob) -- reseta no reload.
export function AlarmsWidget({ scope, areaCodes }: { scope: 'site' | 'area'; areaCodes: string[] }) {
  const [modalOpen, setModalOpen] = useState(false)
  const alarmsQuery = useAlarms()
  const sensors = useSensors().data ?? []
  const areaNameByCode = Object.fromEntries(sensors.map((s) => [s.area.area_code, s.area.name]))

  // Universo dos chips: todas as areas do site, dedup por area_code, ordem
  // estavel por nome. useSensors e assincrono -- enquanto vazio, todasAreas
  // e [] e o default (abaixo) fica vazio ate os sensores chegarem.
  const todasAreas = useMemo(() => {
    const porCodigo = new Map<string, string>()
    for (const s of sensors) {
      if (!porCodigo.has(s.area.area_code)) porCodigo.set(s.area.area_code, s.area.name)
    }
    return Array.from(porCodigo, ([area_code, name]) => ({ area_code, name })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )
  }, [sensors])

  // Default derivado da config: scope='area' com areaCodes definido usa
  // exatamente essas areas (nao depende de useSensors); scope='site' (ou
  // areaCodes=[] em scope='area') usa todas as areas do site.
  const defaultAtivas = useMemo(() => {
    if (scope === 'area' && areaCodes.length > 0) return new Set(areaCodes)
    return new Set(todasAreas.map((a) => a.area_code))
  }, [scope, areaCodes, todasAreas])

  // Override de sessao: null = "sem ajuste ao vivo ainda, usar o default".
  // So vira um Set real no primeiro clique num chip. Isso evita semear um
  // Set vazio "congelado" antes dos sensores carregarem (scope='site'): ate
  // o operador interagir, o efetivo sempre reflete o default mais recente.
  const [override, setOverride] = useState<Set<string> | null>(null)
  const areasAtivas = override ?? defaultAtivas

  function toggleArea(areaCode: string) {
    setOverride((prev) => {
      const base = new Set(prev ?? defaultAtivas)
      if (base.has(areaCode)) base.delete(areaCode)
      else base.add(areaCode)
      return base
    })
  }

  const all = alarmsQuery.data ?? []
  const alarms = all.filter((a) => areasAtivas.has(a.area_code))

  const filtro =
    todasAreas.length > 0 ? (
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro de áreas">
        {todasAreas.map((a) => {
          const ativa = areasAtivas.has(a.area_code)
          return (
            <button
              key={a.area_code}
              type="button"
              aria-pressed={ativa}
              onClick={() => toggleArea(a.area_code)}
              className="min-h-11 shrink-0 rounded-full px-3 text-sm font-semibold outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
              style={
                ativa
                  ? { background: 'var(--color-primary)', color: 'var(--color-panel)' }
                  : { background: 'var(--color-panel)', color: 'var(--color-muted)' }
              }
            >
              {a.name}
            </button>
          )
        })}
      </div>
    ) : undefined

  // "Nenhuma area selecionada" so faz sentido quando ja ha universo de areas
  // (todasAreas carregado) e o operador desligou todas -- distingue essa
  // acao explicita do estado de carregamento inicial (todasAreas=[], que
  // tambem da areasAtivas.size===0 mas nao e uma escolha do operador).
  const mensagemVazio =
    todasAreas.length > 0 && areasAtivas.size === 0 ? 'Nenhuma área selecionada' : undefined

  return (
    <>
      <AlarmPanel
        alarms={alarms}
        areaNameByCode={areaNameByCode}
        onVerMais={() => setModalOpen(true)}
        filtro={filtro}
        mensagemVazio={mensagemVazio}
      />
      {modalOpen && (
        <AlarmsModal alarms={alarms} areaNameByCode={areaNameByCode} onClose={() => setModalOpen(false)} />
      )}
    </>
  )
}
