# Isolamento multi-tenant na API

## Contexto

A API (`api/`, FastAPI) autentica usuários via JWT, mas todas as consultas ao
Odoo rodam com uma conexão de serviço fixa (`get_cliente_servico`, usuário
`admin`). Isso faz a API ignorar as regras de isolamento por cliente já
definidas no Odoo (`ir.rule` em
`addons/afr_sentinela_sensor_monitor/security/security_rules.xml`, que
filtram por `partner_id`), porque essas regras não se aplicam a um usuário
superusuário/serviço.

Resultado: qualquer usuário autenticado, de qualquer cliente cadastrado no
mesmo Odoo, consegue listar, ler e receber em tempo real (SSE) dados de
sensores de **outros** clientes — inclusive via `GET /live` (sem
`sensor_code`), que multiplexa eventos de todos os sensores de todos os
sites para qualquer conexão autenticada.

O problema tem duas metades, porque os dados vivem em dois bancos
diferentes:
- **Dados Odoo** (`sensor`, `hub`, `coletor`, `site`, `alarm_event`,
  `dashboard_config`): o `ir.rule` resolveria o filtro sozinho, se a consulta
  rodasse como o usuário real.
- **Leituras de sensor** (TimescaleDB, tabela `sensor_reading`): não são
  registros Odoo — foram deliberadamente colocadas fora do ORM por volume
  (hypertable, compressão automática, agregados contínuos). `ir.rule` não
  alcança esse banco; precisa de filtro explícito.

## Objetivo

Nenhum usuário autenticado deve conseguir ler ou receber (via SSE) dado de
sensor/site/hub/coletor/alarme que não pertença ao seu próprio cliente
(`partner_id`), em nenhum endpoint da API — hoje ou em endpoints futuros.

Não-objetivo: comportamento do admin (`is_admin`) — decidido que admin
também fica restrito ao(s) seu(s) próprio(s) site(s), sem exceção de
visibilidade cross-tenant.

## Arquitetura

Hoje a API fala com o Odoo sempre como usuário de serviço. A mudança
central: no login, a API mantém a **sessão real do usuário no Odoo** (via
JSON-RPC, sessão obtida com a própria autenticação) em vez de descartá-la —
e usa essa sessão para todas as chamadas Odoo daquele usuário durante a
validade do JWT. Isso faz o `ir.rule` filtrar sozinho os dados que são
modelos Odoo, sem precisar de filtro manual no código da API.

Para o TimescaleDB, a lista de sites que o usuário pode ver é obtida
perguntando ao Odoo (já filtrada pelo `ir.rule`, via a mesma sessão) e vira
um parâmetro **obrigatório** nas funções de consulta — não uma checagem
opcional que um endpoint novo possa esquecer de adicionar.

O SSE segue o mesmo princípio: o filtro de tenant acontece no momento de
decidir para quais conexões repassar cada evento recebido do Postgres
`LISTEN`.

```
Login → API autentica no Odoo, guarda sessão (cache server-side, chave = jti
         do JWT) → devolve JWT (contrato com frontend não muda)

GET /sensores/{code}/historico
  → verificar_token extrai jti → recupera sessão Odoo → obter_sites_permitidos
  → buscar_raw(sensor_code, ..., sites_permitidos) → SQL filtra por site_id
  → resposta

GET /sensores/{code}/live (SSE)
  → mesma resolução de sites_permitidos → registrar(sensor_code, sites_permitidos)
  → live_listener recebe NOTIFY (agora com site_id) → publicar checa cada
    assinante → só repassa se autorizado
```

## Componentes

- **`api/auth.py`** — login passa a guardar a sessão Odoo obtida na
  autenticação (não só `uid`/`partner_id`), associada a um identificador
  dentro do próprio JWT (`jti`). `API_JWT_SECRET` passa a ser obrigatório —
  processo recusa subir sem ele (hoje cai num default hardcoded,
  `dev-secret-troque-em-producao`, achado durante a investigação de
  segurança que originou esta spec).
- **`api/odoo.py`** — novo `get_cliente_usuario` (JSON-RPC, sessão do
  request) substitui `get_cliente_servico` em todos os endpoints que servem
  dado pro dashboard. `get_cliente_servico` continua existindo só para uso
  que não seja resposta direta a uma requisição de usuário (ex.: pipeline de
  ingestão em `ingestao/`, que é código separado e fora do escopo desta
  spec).
- **`api/permissions.py`** (novo) — `obter_sites_permitidos(cliente_usuario)`:
  consulta `sensor_monitor.site` (já filtrado pelo `ir.rule` por rodar como o
  usuário real) e retorna a lista de `site_code` (string) que aquele usuário
  pode ver — é o mesmo formato já usado como valor da coluna `site_id` na
  tabela `sensor_reading` do Timescale (que guarda códigos, não IDs
  numéricos do Odoo), então o resultado é usado direto no filtro SQL sem
  conversão.
- **`api/meta.py`, `api/alarmes.py`** — trocam a dependência de cliente de
  serviço pela de usuário nos endpoints de leitura; não precisam de filtro
  manual, o `ir.rule` já resolve.
- **`api/timescale.py`** — `buscar_raw`/`buscar_agregado` passam a exigir um
  parâmetro `sites_permitidos: list[str]` (sem default); SQL ganha
  `AND site_id = ANY(%s)`.
- **`api/historico.py`** — chama `obter_sites_permitidos` e propaga para
  `buscar_raw`/`buscar_agregado`.
- **`timescale/init.sql`** — o `json_build_object` do trigger
  `notify_sensor_reading` passa a incluir `site_id` no payload do
  `pg_notify` (hoje só manda `sensor_id`/`time`/`valor`).
- **`api/live.py`** — `registrar`/`registrar_global` passam a guardar também
  o conjunto de sites permitidos daquela conexão; `publicar` só entrega o
  evento para uma fila se `payload['site_id']` estiver nesse conjunto.
  `get_live`/`get_live_global` resolvem `sites_permitidos` (via
  `obter_sites_permitidos`) antes de registrar a fila.
- **`api/config.py`** — **explicitamente fora do escopo** (ver seção
  "Fora do escopo").

## Tratamento de erros

- Sessão Odoo expirada/inválida durante a validade do JWT (ex.: Odoo
  reiniciou, sessão revogada) → chamada à API do Odoo falha → endpoint
  responde 401; frontend deve refazer login.
- `API_JWT_SECRET` ausente no ambiente → processo não sobe (fail-fast), em
  vez de usar o default inseguro atual.
- Usuário sem nenhum site liberado → endpoints retornam lista/histórico
  vazios ou stream sem eventos, não erro.
- `sensor_code` existente mas fora dos sites permitidos do usuário → mesma
  resposta que `sensor_code` inexistente (404 genérico) — não diferenciar
  "não existe" de "não é seu", para não confirmar a um usuário não
  autorizado que aquele sensor existe.
- Odoo fora do ar → propaga 503 (comportamento já existente, sem mudança).
- Frontend: erro de permissão (404 uniforme) segue o mesmo caminho que
  qualquer outro erro de fetch hoje — estado `isError` do react-query,
  renderizado inline por widget via `WidgetPlaceholder` (padrão já
  existente, `src/components/WidgetErrorBoundary.tsx` não entra em jogo
  aqui pois não é exceção de render). Sem toast novo.

## Testes

- Dois usuários de clientes diferentes: usuário A pedindo sensor do site do
  usuário B em `GET /sensores/{code}` → não retorna dado (404, não 200 com
  dado alheio).
- Mesmo teste para `GET /sensores/{code}/historico`.
- `GET /sensores/{code}/live` (SSE): evento de outro tenant não chega na
  fila do assinante.
- `GET /live` (multiplex global) com dois tenants publicando ao mesmo
  tempo → cada conexão só recebe eventos dos próprios sites.
- Regressão: fluxo de um único tenant continua retornando os dados certos
  (sem quebrar o caminho feliz existente).
- Subida do processo falha (não sobe) sem `API_JWT_SECRET` no ambiente.
- `obter_sites_permitidos` retorna exatamente os sites que o `ir.rule` do
  Odoo permite para um dado usuário (teste de integração contra Odoo real
  ou fixture equivalente).

## Fora do escopo

- **`api/config.py` / `dashboard_config` usando `SITE_CODE` fixo por
  processo em vez do site do usuário logado.** É uma quebra funcional (não
  vazamento de dado — o usuário não vê dado alheio, só recebe um layout que
  não é o dele), mas incompatível com o pressuposto de instância única
  multi-tenant que esta spec assume para o resto da API. Registrado em
  `TODO.md` como bloqueante de produção, a ser resolvido em separado.
- Exposição da porta 5433 (TimescaleDB) e credenciais hardcoded no
  `docker-compose.yml` — questão de infraestrutura/deploy, não de código da
  API. Vale uma spec própria depois.
- Multi-site por usuário (um cliente com mais de um site) — o desenho atual
  assume que `obter_sites_permitidos` pode retornar mais de um site (e os
  endpoints de leitura já lidam bem com isso, é só uma lista), mas nenhuma
  UI de seleção/troca de site no frontend está sendo desenhada aqui.
