# Dashboard customizável por site — Design

**Data:** 2026-07-19
**Status:** Aprovado (brainstorm)
**Inspiração:** modelo de dashboards do ThingsBoard (open source)

## 1. Objetivo

Permitir que um **admin** monte o layout do dashboard **por site** — escolhendo widgets,
posição e tamanho numa grade livre (drag + resize) — e que **operadores apenas visualizem**
o layout salvo. Substitui o layout hoje hardcoded em `frontend/src/pages/DashboardPage.tsx`.

Extrai do ThingsBoard **apenas o padrão essencial**, cortando a genericidade cara:

| ThingsBoard | Sentinela v1 |
|---|---|
| Layout = 1 blob JSON, backend não parseia | **Mantido** (blob opaco no Odoo) |
| Grid livre gridster | **Mantido** (react-grid-layout) |
| Entity aliases (indireção widget→entidade) | **Cortado** — binding direto a area/sensor do site |
| Multi-state / multi-página | **Cortado** — 1 dashboard por site |
| Layouts por breakpoint | **Cortado** — 1 grid desktop + colapso mobile |
| JS/HTML custom por widget | **Cortado** — catálogo fechado |
| Datasource genérico (qualquer telemetria) | **Cortado** — widget liga a area/sensor |

## 2. Decisões travadas (brainstorm)

1. **Ambição:** admin monta layout por site; operadores só veem. Layout compartilhado por site.
2. **Editor:** grid livre — react-grid-layout, drag + resize, N colunas.
3. **Catálogo v1:** Card de área, Gráfico temporal, Painel de alarmes, KPI (novo).
4. **Persistência:** blob JSON único no model do site (Odoo). Frontend é dono do schema.
5. **Responsivo:** 1 grid desktop editável + colapso automático em 1 coluna no mobile.
6. **Gate de edição:** papel admin via claim JWT / grupo Odoo. Endpoint de escrita valida.

## 3. Schema do layout (o blob)

O **frontend define e valida** a forma (zod). O **Odoo armazena como texto opaco** — não
parseia o interior. Mesmo padrão do ThingsBoard (`JsonNode configuration` no Java).

```ts
// lib/layout/schema.ts
type WidgetType = 'area' | 'timeseries' | 'alarms' | 'kpi'

interface WidgetInstance {
  id: string            // uuid, estável entre edições
  type: WidgetType
  layout: {             // unidades de grid (react-grid-layout)
    x: number
    y: number
    w: number
    h: number
    minW?: number
    minH?: number
  }
  binding: {            // resolvido para dados em runtime
    areaCode?: string   // area | alarms(filtro) | kpi(deriva área do sensor)
    sensorCode?: string // timeseries | kpi
  }
  options?: Record<string, unknown>  // por tipo (ver §4)
}

interface DashboardLayout {
  version: 1
  grid: { cols: number; rowHeight: number; margin: [number, number] }
  widgets: WidgetInstance[]
}
```

- **Validação:** `parseLayout(raw): DashboardLayout` com zod. Entrada inválida → erro
  capturado → cai no `defaultLayout` (nunca quebra a tela do operador).
- **Migração:** `migrate(raw)` usa `version` para atualizar blobs antigos ao schema atual.
  v1 é o primeiro; `migrate` já existe como ponto de extensão (no-op hoje).

## 4. Registry de widgets

Unidade isolada `lib/widgets/registry.ts`. Cada `type` mapeia para um descriptor:

```ts
interface WidgetDescriptor {
  type: WidgetType
  label: string                       // paleta
  icon: ReactNode
  component: ComponentType<WidgetProps>
  defaultSize: { w: number; h: number }
  minSize: { w: number; h: number }
  needs: 'area' | 'sensor' | 'none'   // o que o binding exige
  optionsSchema?: ZodSchema           // valida options no editor
}
```

Adicionar um tipo novo = adicionar 1 entrada no registry. Catálogo v1:

| type | componente base | needs | options |
|---|---|---|---|
| `area` | `AreaCard` (existe) | area | `carouselIntervalMs?` (fallback = config do site) |
| `timeseries` | `TimeSeriesChart` + `WindowSelector` (existem) | sensor | `defaultWindow: '1h'\|'24h'\|'7d'\|'30d'` |
| `alarms` | `AlarmPanel` (existe) | none | `scope: 'site'\|'area'` (+ `areaCode` se area) |
| `kpi` | **`KpiWidget` (novo)** | sensor | `label?: string` |

**KpiWidget (novo):** tile pequeno — valor atual de 1 sensor em destaque
(`text-3xl font-bold`), unidade, cor por estado de alarme (bom/warn/crit). Deriva do
live já existente (`useLiveStatuses`/`useLiveTail`). Reusa `statusVisuals`/tokens AFR.

## 5. Fluxo de dados (render)

```
GET /config → { carousel_interval_ms, layout }
                              │
                    parseLayout(layout)  ── inválido/ausente ──► defaultLayout(areas)
                              │
                        <DashboardGrid>          (react-grid-layout, read-only p/ operador)
                              │
                   para cada WidgetInstance:
                       <WidgetFrame widget>
                          resolve binding (areaCode/sensorCode)
                          → hooks React Query existentes (useSensors/useHistory/useAlarms/live)
                          → renderiza registry[type].component
```

- **`defaultLayout(areas)`** (`lib/layout/defaultLayout.ts`): gera um `area` widget por área
  do site + um `alarms` (scope site) na lateral. Reproduz o comportamento atual quando
  nenhum layout foi salvo. Determinístico (mesma entrada → mesmo layout).
- **`WidgetFrame`** (`components/WidgetFrame.tsx`): resolve o binding para dados e injeta no
  componente; adiciona o "chrome" de edição (handle de arrastar, botão config, botão remover)
  quando em modo edição. É o único ponto que conhece binding→hook.
- Selection state (área/sensor seleccionado hoje via URL) permanece; um `timeseries`/`area`
  pode abrir o `SensorDetailPanel` como hoje (comportamento preservado onde fizer sentido).

## 6. Modo edição (admin)

- Toggle **"Editar"** no `Topbar`, **visível só se `is_admin`** (do contexto de auth).
- Ao entrar: `DashboardGrid` liga drag + resize (react-grid-layout editável).
  - **Paleta** ("+ Adicionar"): lista o registry; ao escolher, cria `WidgetInstance` com
    `defaultSize` e binding vazio; abre config imediatamente.
  - **Config por widget** (popover): escolher area/sensor (dropdown das entidades **do site**)
    + options do tipo. Valida com `optionsSchema`.
  - **Remover** widget.
- Estado de edição vive numa **cópia local** (`useState`) — não toca o servidor até salvar.
- **"Salvar"** → `ConfigApi.saveLayout(layout)` → `PUT /config/layout`. Sucesso → invalida
  query de config. **"Cancelar"** → descarta cópia, volta ao salvo.
- Widget sem binding obrigatório (`needs` não satisfeito) → estado visual "configurar" e
  bloqueia salvar até resolver (ou salva e renderiza placeholder — ver §8 decisão).

## 7. Backend

### 7.1 Odoo — `sensor_monitor.dashboard.config`

Estende o model existente (`addons/afr_sentinela_sensor_monitor/models/dashboard_config.py`),
que já é **único por site**:

```python
layout_json = fields.Text(string='Layout do dashboard (JSON)')   # blob opaco, nullable
layout_version = fields.Integer(string='Versão do schema', default=1)
```

- Sem validação do interior do JSON no Odoo (é blob). Opcional: `@api.constrains` leve que
  confirma que `layout_json`, se preenchido, é JSON parseável (fail-fast contra lixo).

### 7.2 FastAPI — `api/config.py`

- **`GET /config`** (existe): `obter_config` passa a incluir o layout:
  ```python
  return {
      'carousel_interval_ms': ...,
      'layout': json.loads(cfg['layout_json']) if cfg.get('layout_json') else None,
  }
  ```
  `layout: None` → frontend cai no `defaultLayout`.
- **`PUT /config/layout`** (novo):
  - Depends `verificar_token` **+ novo `exigir_admin`** (403 se o claim não for admin).
  - Body: `{ layout: <objeto> }`. Sanity-check leve no servidor: é dict, `version` é int,
    `widgets` é lista. (Validação de forma detalhada fica no frontend/zod.)
  - Upsert do `sensor_monitor.dashboard.config` do `SITE_CODE`: cria se não existir, senão
    escreve `layout_json = json.dumps(body.layout)`, `layout_version = body.layout['version']`.
  - Retorna o layout salvo.

### 7.3 Auth — expor papel admin

- Login (`api/auth.py` + adapter de login) passa a incluir no JWT um claim de papel/admin
  (ex: `is_admin: bool`, derivado de grupo Odoo do usuário). `exigir_admin` lê o claim.
- Frontend `useAuth` expõe `isAdmin` a partir do token para condicionar o botão "Editar".

## 8. Responsivo

- **Desktop:** grid livre de `cols` (default 12), posições `x/y/w/h` do blob.
- **Mobile** (abaixo de um breakpoint, ex: 768px): ignora `x` livre; ordena widgets por
  `(layout.y, layout.x)` e empilha em **1 coluna full-width**, cada widget com altura natural.
  Sem editor mobile (admin edita só desktop). Implementado via `ResponsiveGridLayout` do
  react-grid-layout (breakpoint mobile → `cols: 1`, layout derivado da ordem) ou colapso custom.

## 9. Unidades (arquivos, isolados e testáveis)

**Frontend** (`frontend/src/`):
- `lib/layout/schema.ts` — tipos + zod `parseLayout` + `migrate`
- `lib/layout/defaultLayout.ts` — gerador determinístico a partir das áreas
- `lib/widgets/registry.ts` — descriptors dos 4 tipos
- `components/DashboardGrid.tsx` — react-grid-layout (view + edit)
- `components/WidgetFrame.tsx` — binding→dados + chrome de edição
- `components/widgets/KpiWidget.tsx` — widget novo
- `components/WidgetPalette.tsx` — paleta de adicionar
- `components/WidgetConfigPopover.tsx` — config de binding/options
- `lib/api/contracts.ts` — `ConfigApi` ganha `saveLayout`; `getConfig` retorna `layout`
- `lib/api/mock/config.ts` + `lib/api/real/config.ts` — implementam `saveLayout`
- `lib/queries.ts` — `useConfig` já traz layout; hook/mutation de save
- `lib/useAuth.tsx` — expõe `isAdmin`
- `pages/DashboardPage.tsx` — passa a montar via `DashboardGrid` + layout

**Backend:**
- `addons/afr_sentinela_sensor_monitor/models/dashboard_config.py` — campos novos
- `api/config.py` — `GET` estendido + `PUT /config/layout`
- `api/auth.py` — `exigir_admin` + claim admin no login

## 10. Testes

**Odoo** (`test_dashboard_config.py`, estender):
- Persiste `layout_json` + `layout_version`; unicidade por site mantida.
- (Se constrain optado) rejeita JSON não-parseável.

**FastAPI:**
- `GET /config` retorna `layout` parseado quando salvo; `None` quando ausente.
- `PUT /config/layout` cria (upsert) e atualiza.
- `PUT` **403 para não-admin**; 200 para admin.
- `PUT` rejeita body malformado (não-dict / sem `version` / `widgets` não-lista).

**Frontend:**
- `parseLayout`: aceita válido, rejeita inválido (cai em default); `migrate` no-op v1.
- `defaultLayout`: N áreas → N cards area + 1 alarms; determinístico.
- `registry`: cada type tem component/needs/defaultSize.
- `DashboardGrid`: renderiza widgets do layout (read-only).
- Edição: adicionar / remover / configurar binding / salvar (mock `saveLayout` chamado com
  o layout correto) / cancelar (reverte).
- Colapso mobile: ordena por (y,x) em 1 coluna.
- `KpiWidget`: valor + unidade + cor por estado.
- Gate: botão "Editar" some quando `isAdmin=false`.

## 11. Fora de escopo (YAGNI)

Entity-aliases; multi-state / multi-página; layouts por breakpoint editáveis; JS/HTML custom
por widget; datasource genérico além de area/sensor; múltiplos dashboards por site;
layout por usuário (é por site no v1).

## 12. Questões abertas (resolver na implementação)

1. Widget com binding obrigatório vazio: **bloquear salvar** vs **salvar + placeholder**?
   (Recomendo: permite salvar, renderiza placeholder "configurar" — menos fricção.)
2. `cols` do grid: 12 (default) é suficiente? Confirmar com um layout real de parede.
3. Biblioteca: `react-grid-layout` (madura, ~toque limitado) — confirmar suporte touch se
   o alvo incluir edição em tablet. Edição prevista só desktop → ok.
