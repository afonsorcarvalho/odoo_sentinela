# Design: Configuração do Dashboard via Odoo

## Contexto

O intervalo do carrossel de sensores no `AreaCard` (`frontend/src/components/AreaCard.tsx`) está hardcoded em `CAROUSEL_INTERVAL_MS = 3000`. Objetivo: tornar esse valor configurável a partir do Odoo, e ao mesmo tempo estabelecer um mecanismo geral (extensível) pra configurações de dashboard virem do Odoo — o intervalo do carrossel é o primeiro campo real desse mecanismo, não o único que ele vai ter no futuro.

Granularidade: **por site** (`sensor_monitor.site`), não global — cada instalação/CME pode ter seu próprio intervalo.

## Decisão de abordagem: modelo Odoo dedicado

Novo modelo `sensor_monitor.dashboard.config`, 1-pra-1 com `sensor_monitor.site`, em vez de (a) adicionar campos direto em `site.py` ou (b) um modelo genérico de key-value. Motivo: `site.py` hoje concentra campos de compliance/retenção (RDC15) — misturar config de UI ali degradaria a coesão do modelo. Key-value seria mais flexível mas perde validação/tipo e não gera uma tela Odoo decente sem trabalho extra; com poucos campos conhecidos (e crescimento esperado lento), campos tipados num modelo próprio são mais simples de usar e validar.

## Como a API resolve "o site"

A arquitetura atual já é single-tenant por deployment: 1 processo da API + 1 Odoo DB atende exatamente 1 site (mesmo padrão do `ODOO_DB` fixo em `api/odoo.py`, do `VITE_UNIT_NAME` fixo no frontend, e dos scripts de provisionamento com `SITE_CODE` hardcoded). Nova env var `SENTINELA_SITE_CODE` (mesmo padrão de `ODOO_URL`/`ODOO_DB` em `api/odoo.py`: `os.environ.get('SENTINELA_SITE_CODE', 'SITE-DEMO-01')`) diz à API qual site ela serve.

O modelo Odoo fica correto para multi-site desde já (config é por `site_id`, não global) — só a resolução na API assume 1 site por deployment, igual o resto do sistema hoje. Suporte a múltiplos sites numa única API (site_code por request/header) fica fora de escopo — mudaria também `/sensores` e outras rotas existentes, não é uma mudança isolada desta feature.

## Modelo Odoo: `sensor_monitor.dashboard.config`

Arquivo novo: `addons/afr_sentinela_sensor_monitor/models/dashboard_config.py`.

Campos:
- `site_id`: `Many2one('sensor_monitor.site', required=True, ondelete='cascade')`
- `carousel_interval_ms`: `Integer(default=3000, required=True)` — intervalo de rotação do carrossel de sensores no AreaCard, em milissegundos.

Constraints:
- `_sql_constraints`: `unique(site_id)` — no máximo 1 config por site.
- `@api.constrains('carousel_interval_ms')`: valor mínimo 1000ms (piso — evita configurar um valor tão baixo que o carrossel fique ilegível ou sobrecarregue re-renders), seguindo o mesmo padrão de piso usado em `site.py` (`retention_years` mínimo 5).

Sem criação automática de registro ao criar um site — se não existir config para um site, a API usa os defaults (ver seção API). Isso evita lógica de `create()` override e mantém o modelo simples; o custo é que o registro só existe quando alguém o cria explicitamente pelo Odoo (aceitável, já que o default é idêntico ao valor hardcoded atual).

**View e menu:** view list + form seguindo o padrão de `views/site_views.xml` (grupo único de campos no form, sem abas). Menu novo em `views/menu.xml`, dentro da seção "Cadastro" (`menu_sensor_monitor_cadastro`), ao lado de "Sites", sequence 15 (entre Sites=10 e Áreas=20).

**Segurança:** mesmos grupos já usados por `site.py` em `security/ir.model.access.csv` (`group_sensor_monitor_view` leitura, `group_sensor_monitor_admin` CRUD completo) — é uma config de site, mesma audiência que já administra sites.

**Manifest:** adicionar `models/dashboard_config.py` (via `models/__init__.py`), `views/dashboard_config_views.xml` e a linha correspondente em `ir.model.access.csv`.

## API: novo endpoint `GET /config`

Arquivo novo: `api/config.py`, seguindo exatamente o padrão de `api/meta.py` (`APIRouter()`, `Depends(get_cliente_servico)`, `Depends(verificar_token)`).

Comportamento:
1. Resolve o `site_id` a partir de `SENTINELA_SITE_CODE` (busca `sensor_monitor.site` por `site_code`).
2. Busca `sensor_monitor.dashboard.config` desse site.
3. Se não existir registro: retorna os defaults (`carousel_interval_ms: 3000`) — **não** é erro 404, ausência de config é um estado normal (site ainda não configurado explicitamente).
4. Resposta: `{"carousel_interval_ms": 3000}`.

Registrado em `api/main.py` via `app.include_router(config.router)`, mesmo padrão dos routers existentes.

Autenticação: mesmo `verificar_token` (JWT) que os outros endpoints — não é uma rota pública.

## Frontend

Seguindo o padrão já estabelecido por `MetaApi` (`frontend/src/lib/api/contracts.ts`, `mock/`, `real/`, `index.ts`):

- `types.ts`: `DashboardConfig = { carousel_interval_ms: number }`
- `contracts.ts`: `ConfigApi = { getConfig(): Promise<DashboardConfig> }`
- `mock/configApi.ts`: retorna fixture com `carousel_interval_ms: 3000`
- `real/configApi.ts`: `authFetchJson('/config')`
- `index.ts`: expõe `configApi` (mock ou real conforme `VITE_API_MODE`, mesmo padrão dos outros)
- `queries.ts`: `useConfig()` — `useQuery` com `queryKey: ['config']`; `staleTime` alto (ex: 5 minutos) já que config muda raramente e não precisa refetch agressivo
- `DashboardPage.tsx`: chama `useConfig()`, extrai `carousel_interval_ms` (com fallback 3000 se `isLoading`/erro/sem dado ainda), passa como prop `carouselIntervalMs` pros `AreaCard`
- `AreaCard.tsx`: recebe `carouselIntervalMs: number` como prop nova (em vez da constante local `CAROUSEL_INTERVAL_MS`), repassa pro `useSensorCarousel(group.sensors.length, carouselIntervalMs)`

Fallback: o dashboard nunca fica bloqueado esperando `/config` — renderiza com o default 3000 imediatamente e re-renderiza com o valor real assim que a query resolver (mesmo padrão que `sensorsQuery`/`thresholdResults` já usam hoje, com `?? default`).

## Fora de escopo

- UI custom no Odoo além do form/list padrão gerados pela view XML.
- Auto-criação do registro de config ao criar um site.
- Qualquer campo de configuração além do intervalo do carrossel (o mecanismo é extensível — outros campos entram como specs/plans futuros, um de cada vez).
- Suporte a múltiplos sites numa única API/deployment.
- Atualização em tempo real do dashboard quando a config muda no Odoo (usuário precisa recarregar a página — `staleTime` alto é aceitável).

## Testes a cobrir

**Odoo (Python/Odoo test framework, tag do módulo):**
- Criar `dashboard.config` válido associa corretamente ao site.
- `unique(site_id)`: criar 2 configs pro mesmo site falha.
- `carousel_interval_ms` abaixo de 1000 falha na constraint.

**API (pytest):**
- `GET /config` sem registro de config existente retorna default (`carousel_interval_ms: 3000`).
- `GET /config` com registro existente retorna o valor configurado.
- `GET /config` sem token de auth retorna 401/403 (mesmo comportamento das outras rotas).

**Frontend (vitest):**
- `mockConfigApi`/`realConfigApi` retornam o shape esperado.
- `useConfig()` expõe os dados via react-query.
- `AreaCard` recebe `carouselIntervalMs` como prop e usa esse valor no `useSensorCarousel` (não mais a constante fixa) — atualizar/estender os testes de carrossel já existentes em `AreaCard.test.tsx` pra passar um valor diferente de 3000 e confirmar que o avanço respeita esse valor.
- `DashboardPage` usa o default 3000 enquanto `useConfig()` está carregando/falha.
