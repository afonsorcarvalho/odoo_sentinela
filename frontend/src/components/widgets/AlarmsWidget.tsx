import { useMemo, useState, type CSSProperties } from 'react'
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

  // Universo dos chips: UNIAO das areas de useSensors com as areas presentes
  // nos alarmes correntes (useAlarms), dedup por area_code, ordem estavel por
  // nome. useAlarms e useSensors sao queries independentes sem ordem
  // garantida -- se o universo dependesse so de useSensors, enquanto essa
  // query nao resolvesse (ou retornasse vazia) o default ficaria vazio e, em
  // scope='site', TODOS os alarmes reais seriam filtrados para fora (ver
  // CRITICAL no design doc). Alarmes cujo area_code nao tem sensor
  // correspondente tambem entram, com nome = areaNameByCode[code] ?? code
  // (mesmo fallback usado pelo AlarmItem), para nunca ficarem sem chip.
  const todasAreas = useMemo(() => {
    const porCodigo = new Map<string, string>()
    for (const s of sensors) {
      if (!porCodigo.has(s.area.area_code)) porCodigo.set(s.area.area_code, s.area.name)
    }
    for (const a of alarmsQuery.data ?? []) {
      if (!porCodigo.has(a.area_code)) porCodigo.set(a.area_code, areaNameByCode[a.area_code] ?? a.area_code)
    }
    return Array.from(porCodigo, ([area_code, name]) => ({ area_code, name })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )
  }, [sensors, alarmsQuery.data, areaNameByCode])

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

  // Chip "Todas" (toggle-all, ver docs/superpowers/specs/2026-07-20-alarme-filtro-polish-design.md):
  // estado 3-valores derivado de areasAtivas (efetivo) vs o universo todasAreas.
  // Tap: se todas ativas -> limpa (Set vazio explicito, NAO null -- null cairia
  // de volta no default via areasAtivas = override ?? defaultAtivas e o "limpar"
  // nao pegaria); senao (mixed ou nenhuma) -> ativa todas.
  const totalAreasUniverso = todasAreas.length
  const totalAreasAtivas = todasAreas.filter((a) => areasAtivas.has(a.area_code)).length
  const todasPressed: boolean | 'mixed' =
    totalAreasUniverso > 0 && totalAreasAtivas === totalAreasUniverso
      ? true
      : totalAreasAtivas === 0
        ? false
        : 'mixed'

  function toggleTodas() {
    if (todasPressed === true) {
      setOverride(new Set())
    } else {
      setOverride(new Set(todasAreas.map((a) => a.area_code)))
    }
  }

  // Chips ~50% menores no VISUAL, alvo de toque compacto (min-h-9 = 36px, acima
  // do piso WCAG 2.5.8 = 24px; abaixo do ideal 44px de luva, trade-off aceito
  // pelo usuario p/ aproximar as linhas quando o filtro quebra em varias). O
  // peso visual (a mancha colorida) e o alvo tocavel sao elementos DIFERENTES:
  // o <button> e transparente e so define a hit-area (min-h-9, min-w-11,
  // flex+centralizado); quem carrega a cor/fundo e um <span> interno menor
  // (py-1, texto text-[11px]/font-medium). O foco (focus-visible) fica no
  // botao, entao o anel de foco cobre a hit-area toda, nao so o pill pequeno.
  const chipButtonClass =
    'flex min-h-9 min-w-11 shrink-0 items-center justify-center rounded-full bg-transparent px-1 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]'
  const chipPillClass =
    'rounded-full px-2 py-1 text-[11px] font-medium transition-[background-color,color,transform] duration-200 ease-out active:scale-95 motion-reduce:transition-none motion-reduce:active:scale-100'

  // Estilo do pill por estado -- 3 aparencias distintas (produto medico: um
  // subconjunto ativo ("mixed") nao pode parecer igual a "nenhuma selecionada"
  // (false), senao o operador le "Todas" apagado e confia num alarme filtrado
  // como se estivesse all-clear). true = preenchido primary; false = panel
  // liso; mixed = panel + borda primary (sinaliza "parcialmente ligado" sem
  // ocupar o peso visual do preenchido).
  function pillStyle(pressed: boolean | 'mixed'): CSSProperties {
    if (pressed === true) return { background: 'var(--color-primary)', color: 'var(--color-panel)' }
    if (pressed === 'mixed')
      return {
        background: 'var(--color-panel)',
        color: 'var(--color-muted)',
        border: '1.5px solid var(--color-primary)',
      }
    return { background: 'var(--color-panel)', color: 'var(--color-muted)' }
  }

  const filtro =
    todasAreas.length > 0 ? (
      <div className="flex flex-wrap gap-x-2 gap-y-1" role="group" aria-label="Filtro de áreas">
        <button type="button" aria-pressed={todasPressed} onClick={toggleTodas} className={chipButtonClass}>
          <span className={chipPillClass} style={pillStyle(todasPressed)}>
            Todas
          </span>
        </button>
        {todasAreas.map((a) => {
          const ativa = areasAtivas.has(a.area_code)
          return (
            <button
              key={a.area_code}
              type="button"
              aria-pressed={ativa}
              onClick={() => toggleArea(a.area_code)}
              className={chipButtonClass}
            >
              <span className={chipPillClass} style={pillStyle(ativa)}>
                {a.name}
              </span>
            </button>
          )
        })}
      </div>
    ) : undefined

  const all = alarmsQuery.data ?? []
  const alarms = all.filter((a) => areasAtivas.has(a.area_code))

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
